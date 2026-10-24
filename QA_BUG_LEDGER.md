# QA 真实故障与修复账本 (QA_BUG_LEDGER.md)

---

## BUG-01：模型选择与真实执行模型不一致及 2.0/2.5 图像模型缺失

- **严重程度**：P0（阻塞级）
- **复现路径**：
  1. 在无限画布中选中生图节点，查看模型下拉列表，仅包含 `gpt-image-1.5`，缺失主流 2.0 / 2.5 规格。
  2. 在视频节点选择 `veo-quality` 或 `veo-fast` 并将时长设为 6s，提交生成。
  3. 查看任务入库记录与执行命令，模型均被强制覆盖为默认的普通模型 `omni-flash`。
- **预期行为**：
  1. 用户选择 `gpt-image-2` 或 `gpt-image-2.5` 能正确发起生成并返回高精写实图片。
  2. 选择 Veo 细分模型（`veo-lite` / `veo-fast` / `veo-quality`）并指定 4s/6s/8s 时，系统应严格保留用户选中的特定型号，仅 10s 时才收敛至 Omni。
- **实际行为**：
  - 前端和后端缺少 2.0/2.5 选项；且当时长为 6s 时，代码中存在 `if int(task.duration_sec) in (6, 10): flow_model = "omni-flash"` 强制降级覆盖。
- **根因分析**：
  1. `use-config-store.ts` 与 `canvas_video_compat.py` 未挂载 `gpt-image-2` 与 `gpt-image-2.5` 渠道规格。
  2. `canvas_video_compat.py` 和 `worker.py` 在判断模型逻辑时，把时长 6s 与 10s 并列处理，误将 6s 视为 Omni 独占时长并硬覆盖。
- **修复涉及文件**：
  - `video_farm/canvas_video_compat.py`
  - `video_farm/worker.py`
  - `D:\AI-Projects\infinite-canvas\web\src\lib\model-spec.ts`
  - `D:\AI-Projects\infinite-canvas\web\src\stores\use-config-store.ts`
- **复测结果**：**PASS**
  - 实测调用 `gpt-image-2` 与 `gpt-image-2.5` 均成功返回 200 OK 并解码 2.5MB 高清 Base64。
  - 实测调用 `veo-fast` 6s 任务，入库与下发命令均保留 `model=veo-fast, duration=6`。
- **剩余风险**：无。

---

## BUG-02：Flow 视频生成成功但回显缓慢 / 播放延迟

- **严重程度**：P1（严重体验缺陷）
- **复现路径**：
  1. 在无限画布中触发 Flow 视频节点生成。
  2. 8088 调度器与上游生成完成后，任务状态已变为 `completed`。
  3. 画布节点依然处于持续 loading 转圈状态，等待数秒至数十秒后才渲染播放器。
- **预期行为**：
  - 任务轮询一旦检测到 `completed`，节点立即渲染成片并就绪播放，后台静默持久化缓存。
- **实际行为**：
  - 前端必须等待完整的 `storeGeneratedVideo`（包含将数兆至数十兆视频完整 fetch 转为 Blob、写入 IndexedDB、读取元数据等）全部阻塞完成后才调用 `applyGeneratedVideo`。
- **根因分析**：
  - `project.tsx` 中的异步流处理顺序导致全量文件落地存储阻塞了前端 UI 视口的渲染触发。
- **修复涉及文件**：
  - `D:\AI-Projects\infinite-canvas\web\src\pages\canvas\project.tsx`
- **复测结果**：**PASS**
  - 收到任务完成时，第一时刻将 `taskResult.url` 写入节点 `content` 与 `videoUrl`，播放器即时呈现，实现零等待渲染。
- **剩余风险**：无。

---

## BUG-03：Google Vids 完全不能生成（“Vids 工程必须为 docs.google.com/videos 的 HTTPS 地址”）

- **严重程度**：P0（阻塞级）
- **复现路径**：
  1. 在无限画布中选择 Google Vids 模型并点击生成。
  2. 任务状态直接报错失败，错误提示：`Vids 工程必须为 docs.google.com/videos 的 HTTPS 地址`。
- **预期行为**：
  - 画布工程发起 Vids 视频生成时，自动化引擎应自动导航至 `https://docs.google.com/videos/create` 并进入工作流。
- **实际行为**：
  - 任务未提交直接抛出 `VideoRequestError` 并硬中断。
- **根因分析**：
  - 无限画布将自身的项目 ID（如 `proj_test_suite_001`）直接透传为 `task.project_id`。
  - `vids_worker.py` 将其误当成了上游 Google Vids 文档 URL，校验 `not task.project_id.startswith("https://docs.google.com/videos/")` 失败直接抛错。
- **修复涉及文件**：
  - `video_farm/canvas_video_compat.py`
  - `video_farm/vids_worker.py`
- **复测结果**：**PASS**
  - 画布 project_id 被作为 Session Affinity 键留存，上游 `task.project_id` 自动清空让 Vids 导航至 `/create`。
- **剩余风险**：无。

---

## BUG-04：Flow 404 Project Not Found 与 Gemini 模型网页不可用

- **严重程度**：P1（高优先级）
- **复现路径**：
  1. 画布提交 Flow 视频任务，Chrome 自动化导航打开 `https://flow.google.com/project/proj_test_suite_001`，页面提示 `Project not found` (404)。
  2. 提交 Gemini 视频任务，报错 `所选 Gemini 模型 gemini 在该账号网页不可用`。
- **预期行为**：
  1. Flow 任务应打开该账号已绑定的真实 Google Flow UUID 工程。
  2. Gemini 默认任务不应在网页下拉菜单中盲目匹配不存在的选项“gemini”。
- **实际行为**：
  - Flow 打开错误 URL 触发 404；Gemini 在菜单中匹配失败中断。
- **根因分析**：
  1. 画布工程 ID 被透传至 Flow `--project`，破坏了 profile 已绑定的合法工程 UUID。
  2. `gemini_worker.py` 将 `task.model="gemini"` 作为关键词去网页匹配下拉按钮，且携带了 Chrome 告警参数 `--disable-blink-features=AutomationControlled`。
- **修复涉及文件**：
  - `video_farm/canvas_video_compat.py`
  - `video_farm/worker.py`
  - `video_farm/gemini_worker.py`
- **复测结果**：**PASS**
  - 画布工程解耦，自动映射到 `flow_project_id`；Gemini 识别默认模式，安全绕过菜单盲点。
- **剩余风险**：无。

---

## BUG-05：生成后引用图片提示“图片不存在”（多图分号拼接路径解析错误）

- **严重程度**：P0（阻塞级）
- **复现路径**：
  1. 在多图参考（Ingredients）模式下上传多张图片（如 2~3 张）。
  2. 提交后 worker 校验提示：`图片不存在：C:\...\start.png;C:\...\ref2.png`。
- **预期行为**：
  - 系统正确识别多图列表，逐个验证每张参考图片的存在性与格式。
- **实际行为**：
  - 后端直接将以分号拼接的字符串作为单个 Windows 文件路径进行 `Path(p).is_file()` 校验，必然返回 False。
- **根因分析**：
  - `worker.py`、`scheduler.py`、`web.py` 在多处未先执行 `.split(";")` 拆分即直接转为 `Path` 对象。
- **修复涉及文件**：
  - `video_farm/worker.py`
  - `video_farm/scheduler.py`
  - `video_farm/web.py`
- **复测结果**：**PASS**
  - 编写专用多图路径解析单元测试与实测脚本，全部正确解析为独立的单文件对象。
- **剩余风险**：无。

---

## BUG-06：生图接口网络/DNS超时报错 (chatgpt.com i/o timeout) 与守护进程高并发误杀

- **严重程度**：P1（高可用阻断）
- **复现路径**：
  1. 用户在无限画布或兼容接口发起生图时，偶尔抛出报错弹窗：`Post "https://chatgpt.com/backend-api/codex/images/generations": dial tcp: lookup chatgpt.com: i/o timeout`。
  2. 查看后台 `watchdog.log`，发现高负载生图期间，守护脚本每 5s 对 `/v1/models` 执行超时仅 3s 的检查，3 次超时即触发 `Stop-Process -Force` 暴力误杀 CLIProxyAPI 进程。
  3. 进程重启期间或科学上网代理（Clash 7897）偶发 DNS 延迟时，由于配置中 `request-retry: 0`，未进行任何重试即向前端抛出 504 错误。
- **预期行为**：
  1. 守护进程具备充足的容限（单次健康检测超时 10s，连续 6 次失败才重启），杜绝生图耗时引起的误杀。
  2. 代理服务启用自动重试机制（`request-retry: 3`），瞬态网络抖动时自动切换或重试。
  3. 兼容接口与画布前端具备自动重试（2 次尝试）与超时优雅转译，向用户给出清晰的代理检查建议而非底层 Go 报错堆栈。
- **实际行为**：
  - 守护脚本频繁误杀 CLIProxyAPI，前端直接暴露裸错误字符串 `dial tcp: lookup chatgpt.com: i/o timeout`。
- **修复涉及文件**：
  - `C:\Users\win10\Desktop\CLIProxyAPI_7.0.2_windows_amd64\config.yaml`
  - `C:\Users\win10\Desktop\CLIProxyAPI_7.0.2_windows_amd64\run-cli-proxy-api-daemon.ps1`
  - `video_farm/canvas_video_compat.py`
  - `D:\AI-Projects\infinite-canvas\web\src\services\api\image.ts`
- **复测结果**：**PASS**
  - 实测调用 `gpt-image-2`（1.0MB Base64）与 `gpt-image-2.5`（2.61MB Base64）连续生成均返回 200 OK。
  - 守护进程日志稳定，未再出现因生图耗时导致的异常误杀。
  - 前端与后端适配层均已装载重试与中文网络引导机制。
- **剩余风险**：外部科学上网代理节点完全断网时需用户确认本地代理状态。
