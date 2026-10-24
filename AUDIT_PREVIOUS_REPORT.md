# 上一轮验收声明反向审计报告 (AUDIT_PREVIOUS_REPORT.md)

---

## 1. 审计概述与原则

根据最高优先级任务要求，本报告对上一轮宣布的“100% 完成”及相关数据进行独立、无偏见的反向证据链审查。
评级标准严格限定为：
- **VERIFIED**：有明确物理文件、真实日志或机器断言证据支持。
- **PARTIAL**：仅部分环节有证据，或测试范围与声明范围不完全匹配。
- **UNVERIFIED**：缺少必要执行证据或记录为空。
- **CONTRADICTED**：发现相反的客观证据或事实相悖。

---

## 2. 逐项反向审计明细

### 项 A：Git 提交 `cf38801` 是否真实存在且属于本项目
- **审计结论**：**VERIFIED**
- **命令证据**：`git log -n 1 cf38801 --stat`
- **结果记录**：
  ```
  commit cf388011e495eded8294d9e9e9f5e3aa3a44bf5f
  Author: malongzhao <malongzhao@gmail.com>
  Date:   Sat Oct 24 13:24:38 2026 +0800
  fix: 修复生图DNS代理超时与守护进程误杀，完成无限画布全功能验证与审计
  16 files changed, 622 insertions(+), 67 deletions(-)
  ```
- **判定**：提交真实存在于 `C:\Users\win10\Documents\ChatGPT\视频制作`，归档文件完整。

---

### 项 B：提交实际修改的文件清单
- **审计结论**：**VERIFIED**
- **证据文件**：
  1. `MODEL_CAPABILITIES.json`
  2. `QA_BUG_LEDGER.md`
  3. `QA_EVIDENCE/canvas_live_view.png`
  4. `QA_EVIDENCE/canvas_live_view_fixed_badge.png`
  5. `QA_EVIDENCE/test_golden_star.png`
  6. `QA_FINAL_REPORT.md`
  7. `QA_TEST_MATRIX.csv`
  8. `ROLLBACK.md`
  9. `docs/devlog/2026-10-24-008.md`
  10. `docs/project-state.md`
  11. `video_farm/canvas_video_compat.py`
  12. `video_farm/gemini_worker.py`
  13. `video_farm/scheduler.py`
  14. `video_farm/vids_worker.py`
  15. `video_farm/web.py`
  16. `video_farm/worker.py`

---

### 项 C：源码改动是否与报告所述修复一致
- **审计结论**：**VERIFIED**
- **核查内容**：
  - `canvas_video_compat.py`：包含 120s 超时、重试循环、DNS 错误转译及工程 ID 虚拟化解耦；
  - `worker.py`：包含 Veo 6s 保持与多图分号拆分；
  - `vids_worker.py`：去除了对画布虚拟 project_id 的强前缀校验；
  - `gemini_worker.py`：移除了 `--disable-blink-features=AutomationControlled` 启动告警参数。

---

### 项 D：是否存在未提交修改或运行服务使用旧代码
- **审计结论**：**CONTRADICTED**（发现重大偏差）
- **核查证据 1（运行服务代码滞后）**：
  - 检查 8088 端口服务进程 PID 40120，其创建时间为 `13:10:32`；
  - 而 `canvas_video_compat.py` 代码修改发生于 `13:21:40`；
  - `python.exe -m video_farm.web` 启动时未启用 `--reload` 自动热载，导致 8088 运行进程在内存中持有修改前的旧字节码！
- **核查证据 2（无限画布未提交）**：
  - 在 `D:\AI-Projects\infinite-canvas` 执行 `git status`，存在 12 个未提交修改文件（包含 `use-config-store.ts`、`image.ts`、`project.tsx` 等核心文件）以及未跟踪的 `web/src/lib/model-spec.ts`。
- **整改要求**：重启 8088 服务以使补丁生效，并在 `infinite-canvas` 中提交或同步对应代码。

---

### 项 E：六份交付物真实性与内容完整性
- **审计结论**：**VERIFIED**
- **文件检查**：
  - `QA_BUG_LEDGER.md` (8,688 bytes, 包含 BUG-01 到 BUG-06 详细账目)
  - `QA_TEST_MATRIX.csv` (2,808 bytes, 包含 19 个测试矩阵条目)
  - `QA_EVIDENCE/` (包含 3 个媒体文件)
  - `QA_FINAL_REPORT.md` (8,053 bytes, 包含五大部分)
  - `MODEL_CAPABILITIES.json` (4,835 bytes, 包含结构化能力)
  - `ROLLBACK.md` (2,954 bytes, 包含完整还原指令)

---

### 项 F：QA_EVIDENCE 中的素材是否来自真实测试
- **审计结论**：**PARTIAL**
- **核查结果**：
  - `test_golden_star.png` (SHA256: `8B2A53C7...`, 1.24MB)：证实为真实生成的写实星空金球图片，Base64 解码正常。
  - `canvas_live_view.png` 与 `canvas_live_view_fixed_badge.png`：证实为 Playwright 针对 `http://127.0.0.1:3000/canvas/proj_test_suite_001` 截取的真实全景浏览器图。
  - **不足点**：缺少真实视频成片 mp4 文件的本地校验和与关键帧截图证据。

---

### 项 G：9 项 skipped 的真实原因与有效性审查
- **审计结论**：**CONTRADICTED**（发现因跳过而掩盖的隐性 Bug）
- **核查结果**：
  - 9 项 skipped 分布为：
    - `video_farm/tests/test_live_e2e_sanity.py:14`（1 项）
    - `video_farm/tests/test_vids_process_regression.py:71`（8 项）
  - **关键发现**：当手动注入环境变量 `$env:VIDEO_FARM_LIVE_E2E="1"` 执行该测试时，测试立即发生 **FAILURE**：
    `AssertionError: Missing Vids overview`（因 `/api/vids/overview` 仅返回 `workflows_count`，而契约检查要求 `total_workflows`）。
  - **结论**：跳过此测试掩盖了一个真实存在的接口字段契约不一致缺陷，必须予以修复！

---

### 项 H：真实视频生成测试实际覆盖情况
- **审计结论**：**CONTRADICTED**（声明与数据库记录存在实质差异）
- **核查证据**：
  - 查询数据库 `video_farm_data/tasks.db` 最近的任务记录：
    - `task_dfce2411c9c0` (veo-lite 4s): `cancelled`
    - `task_6b425b82b718` (veo-fast 6s): `cancelled`
    - `task_49d6cd698761` (veo-quality 8s): `cancelled`
    - `task_5d966f29521a` (vids Omni 8s): `cancelled`
    - `task_3b76f37c2007` (omni-flash 8s): `completed` (生成了真实的 3.59MB `task_3b76f37c2007.mp4`)
  - **结论**：上一轮测试矩阵中，除 `omni-flash` 产生真实成片外，Veo 4s/6s/8s 及 Vids 的测试任务均为在参数下发与前置校验后即取消的“探针测试”，并未由云端实际渲染成片。报告将其简单标注为 PASS 存在夸大成分，应准确标注为“参数与模型透传校验通过 (PROBE_VERIFIED)”，并将“成片生成”与“参数校验”明确区分。

---

### 项 I：Playwright 自动化是否完整覆盖点击、生成、回填全链路
- **审计结论**：**PARTIAL**
- **核查证据**：
  - 查看 `test_canvas_e2e_full.py`：脚本执行了打开主页、新建画布、检查工具栏、页面刷新与状态恢复；
  - 但在节点渲染和视频播放验证中，脚本直接打开了预埋的 `proj_test_suite_001` 工程，并断言其视频元素 `readyState=4`；
  - 脚本**未在浏览器中实际点击图像或视频节点的“生成”按钮**并等待数十秒直至异步回填完成。

---

### 项 J：Token 消耗与执行耗时口径
- **审计结论**：**VERIFIED**
- **核查结果**：
  - `tokensUsed: 3429834, timeUsedSeconds: 1924` 是 Codex 内部平台 `get_goal` 工具记录的宿主多轮会话开销，并非调用上游模型生成的计费 Token。

---

## 3. 本阶段审计总结与整改行动项

| 发现的真实问题 | 严重级别 | 整改行动 |
| :--- | :--- | :--- |
| **8088 进程持有旧代码** | P0 | 重启 8088 服务，验证最新接口已正确装载 |
| **`/api/vids/overview` 字段缺失导致 `test_live_e2e_sanity` 失败** | P1 | 在 `vids_router.py` 中补充 `total_workflows` 字段，使该用例在开启时不报错 |
| **测试矩阵将探针测试混同为真实生成** | P1 | 修正测试矩阵分类，明确标注“参数校验通过”与“真实成片生成”的区别 |
| **Playwright 未覆盖真实点击生成交互** | P1 | 编写包含真实点击生图节点并等待产物回填的自动化交互测试脚本 |
| **`infinite-canvas` 改动未入库** | P2 | 审查并保存前端工程改动与提交记录 |
