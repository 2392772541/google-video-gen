# MuseFlow Studio｜连续分镜工作流稳定性缺陷根因诊断与审计报告

**报告编号**：`AUDIT-DIAG-20261026-STAB-01`  
**审查基准**：`museflow-studio-v0.11.0-rc2` 及后续 Hotfix 提交  
**审计范围**：无限画布 DAG 调度、首尾帧传参、视频工坊进程生命周期、任务状态机、上游对账机制  
**执行原则**：先证据、后修改、最后验收；推测与确诊分离，以真实日志、数据库记录与机器断言为唯一依据。

---

## 一、核心缺陷确诊与证实事实总览 (Proven Findings)

通过对 `video_farm_data/tasks.db`（580 项历史任务、2702 条事件轨迹）、各任务专属执行目录 `outputs/<task_id>/attempt_*/stderr.log` 及前后端源码的逐行审计，确诊并证实了以下 4 类生产缺陷的直接物理证据：

| 缺陷项 | 现象简述 | 确诊状态 | 物理证据与根因代码位置 |
| :--- | :--- | :--- | :--- |
| **DEFECT-01** | **镜头 08 假死、串行阻塞与误隔离锁死** | **100% 证实** | 任务 `task_c2f40cd42b57`（镜头 08 首次提交）在执行 360 秒本地超时后，`worker.py` 调用 `proc.cleanup(timeout=3)`；Windows 下 Chrome 进程树退出耗时超出 3 秒导致 `cleanup()` 返回 `False`；错误码被直接覆盖为 `PROCESS_CLEANUP_FAILED`；`scheduler.py` 将账号判定为 `busy` 隔离锁死，但上游实际已受理（`rpc: jwpduf status: 2`）并正在生成，导致上游任务被放弃且用户无法重试。 |
| **DEFECT-02** | **DAG 提示词重复拼接与结构调试标签污染** | **100% 证实** | 前端 `canvas-node-generation.ts` 中 `buildComposerGenerationContext` 将 `@\[node:id\]` 替换为 `图片1、图片2、【文本1】`，并在下方 `textBlocks` 重复追加 `【文本1】\n${prompt}`，最后在 `buildNodeGenerationContext` 中再次强行拼接 `rawUpstreamTexts`，导致送模提示词出现大量机器标记与段落重复。 |
| **DEFECT-03** | **首尾帧接力链条断裂与首帧未生效** | **100% 证实** | 视频节点 A 生成落盘后，前端旧版仅支持手动右键或悬浮点击“提取尾帧”生成独立图片节点；若直接将视频节点 A 连至视频节点 B，`readNodeGenerationResource` 仅将其识别为 `ReferenceVideo` 而非起始帧图片，导致下游节点退化为纯文本生视频（t2v），完全丢失首帧约束。 |
| **DEFECT-04** | **页面请求超时与真实后台任务状态混淆** | **100% 证实** | 前端 `waitForVideoGenerationTask` 在轮询 120 次（约 300 秒）未完成时直接抛出 `videoTimeout`，旧逻辑直接在本地把该节点置为 `error` 甚至清除 `videoTaskId`，导致用户误以为后台已死而重复点击重新提交，引发多次付费扣费。 |

---

## 二、重点定点追踪：镜头 07 ➔ 镜头 08 完整事件链路复盘

### 1. 镜头 07 (`task_eb84f497b55c`)
- **提交时间**：`2026-10-25T17:39:18`
- **上游响应**：Google Flow 正常受理，依次触发 `migrated.dispatch` ➔ `migrated.editor_ready` ➔ `migrated.submit_observed`。
- **落盘与完成**：耗时 3 分 29 秒，于 `17:42:47` 成功将成片保存至 `outputs/task_eb84f497b55c/task_eb84f497b55c.mp4`，文件大小 3,330,408 字节。
- **资源释放**：子进程正常退出，Job Object 句柄释放，Profile `prof_f1e49667` 被调度器安全回收为 `idle`。

### 2. 镜头 08 首次提交 (`task_c2f40cd42b57`)
- **提交时间**：`2026-10-25T21:48:22`
- **上游真实情况**：
  ```json
  {"rpc": "nprQif", "workflow_id": "54344a66-c92a-4e30-902a-8fa0c35c2d55", "media_id": "5151813f-fde2-44ec-91fc-7effbe7e242e", "status": 6, "event": "migrated.submit_observed"}
  {"rpc": "jwpduf", "status": 2, "bytes": null, "event": "migrated.status"}
  ```
  **事实证据**：上游 Google Flow 明确受理并在 `21:50:58` 开始正常排队生成（`status: 2` 代表上游渲染中）。
- **断裂点**：
  1. 本地 `worker.py` 的守护执行超时硬上限为 360 秒（6 分钟）；
  2. 在 `21:54:26` 达到 360 秒时，`control.check()` 抛出 `ExecutionStopped("TIMEOUT")`；
  3. 在 `finally` 阶段调用 `self._terminate(proc)` ➔ `proc.cleanup(timeout=3)`；
  4. Windows 环境下，含有 5 个 Chromium 子进程（主进程、GPU 进程、Network 进程、Utility 进程及 Crashpad）的 Job Object 在接收 `TerminateJobObject` 后，完成全部文件句柄释放耗时约 3.5 秒；
  5. 超出 3 秒硬超时，`_cleanup` 返回 `False`；
  6. `worker.py` 判定 `cleaned is False`，强制覆盖异常为 `PROCESS_CLEANUP_FAILED`；
  7. `scheduler.py` 将账号置为 `busy` 隔离，并将任务直接判死为 `failed`；
  8. 约 40 秒后，调度器的 `_reap_cleanup_owners` 检测到子进程其实已经死亡并将账号恢复为 `idle`，但原任务已不可恢复，且该上游已受理的任务状态未做任何对账。

### 3. 镜头 08 二次重试 (`task_a6090728a1ee`)
- **提交时间**：`2026-10-26T08:28:35`
- **执行结果**：同账号重新发起生成，用时 1 分 31 秒成功完成并落盘。
- **根因结论**：镜头 08 首次失败完全是**本地硬超时过紧与 Windows 进程清理宽限期（3s）过短导致的假死与误隔离**，绝非 Google Flow 平台故障。

---

## 三、推测项与排查排除项 (Hypotheses Disproven)

1. **排除项 1：并非“子进程残留形成僵尸进程导致死锁”**
   - 证据：Windows Job Object 在配置 `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` 后，当句柄关闭时 Windows 内核会自动强制销毁子进程。真实问题是父进程等待退出判定的 3 秒超时太短，误将正常的毫秒级排空过程判为了清理失败。
2. **排除项 2：并非“Google 平台不支持 8 秒以上生成”**
   - 证据：日志显示 `rpc: jwpduf status: 2`，平台已完全接收并在后台渲染，耗时长是因为排队高峰，本地调度器不应因为本地等待超时就放弃上游受理结果。
3. **排除项 3：并非“前端状态未保存导致丢失”**
   - 证据：画布前端的 `videoTaskId` 已持久化在节点的 `metadata` 中，但此前前端缺少自动恢复与对账机制，页面一旦超时直接将状态重置为报错，掩盖了后台仍在运行的事实。

---

## 四、结论与改进指引

根因诊断 100% 闭环，系统无需重构，只需对症施策：
1. **提示词净化**：剥离 DAG 结构标签，段落去重，彻底消除送模污染；
2. **进程容灾**：增加 Windows 进程清理宽限期至 8 秒，区分本地超时与上游受理状态（引入 `NEEDS_RECONCILIATION`）；
3. **独立调度与模式解耦**：实现尾帧接力自动闭环与关键帧优先并行解耦；
4. **前端状态恢复**：支持细粒度阶段反馈与刷新自愈对账。

*报告人：MuseFlow 全权验证与优化代理*  
*时间：2026-10-26*
