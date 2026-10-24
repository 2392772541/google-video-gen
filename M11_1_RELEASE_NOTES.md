# MuseFlow Studio v0.11.0-rc1 发布说明书 (Release Notes)

## 一、版本概述
- **版本号**: `museflow-studio-v0.11.0-rc1` (Release Candidate 1)
- **发布日期**: 2026-10-25
- **定位**: 经过 M7~M11.1 全流程审计、物理证据核验、生产可靠性加固与 8 镜头 9:16 竖屏成片正式交付的发布候选版本。

---

## 二、核心功能特性 (Key Features)
1. **平台级深度原生集成**:
   - 彻底摆脱 Chrome 扩展环境依赖，提供原生 Web 运行垫片 (`runtime-adapter.js`)；
   - 双引擎调度：视频工坊本地引擎 (Video Farm Engine) 直连 8088 后端，与 Google Flow、Google Vids、Gemini 网页端及 8317 多模型网关深度打通。
2. **镜头级精细化生产与版本流转**:
   - 稳定镜头身份识别 (`shotId`) 与候选管理 (V1/V2...)；
   - 候选版本切换后自动重置审片状态为 `PENDING_REVIEW`，严禁静默沿用旧审核；
   - 尾帧连续性与失效感知：上游重生成后下游触发 `STALE_REFERENCE` 警示，防误连。
3. **DAG 依赖感知单并发批量调度器**:
   - 串行批量调度 (`concurrency=1`)，严格防止并发打爆系统内存与显存；
   - 故障强隔离：单镜头网络中断或超时不阻断其他镜头独立结果，支持单镜头重试恢复。
4. **全自动技术质检 (QC) 与广播级 FFmpeg 精确合成**:
   - 自动运行黑帧检测 (`blackdetect`) 与冻结画面检测 (`freezedetect`)；
   - 彻底修复分镜量化截断累积误差，将 `fps=30` 统一提升至 `concat` 连续流后置执行；
   - 交付 1080x1920 (9:16 竖屏超清) 8 镜头成片，实现 **540 帧 / 18.000000 秒** 零物理误差对齐。
5. **端到端断点恢复与防重复扣费保护**:
   - 引入客户端 `requestId` 与服务端 `_IDEMPOTENT_REQUEST_CACHE`，相同请求幂等复用；
   - 响应丢失自动对账机制：在网络中断未收到响应时自动反查对账，未确认状态安全挂起进入 `NEEDS_RECONCILIATION`，严禁盲目自动重试二次扣费。
6. **便携式完整工程归档迁移**:
   - 采用纯相对路径 `assets/` 组织工程资产与全量元数据，生成可移植 ZIP 包；
   - 经全新独立临时目录实测验证，支持 100% 离线解包、素材哈希比对与离线成片重新导出。

---

## 三、运行环境与系统要求 (Runtime Requirements)
- **操作系统**: Windows 10 / 11 64-bit
- **Python**: 3.10+ (依赖 FastAPI, Uvicorn, Playwright, Requests)
- **Node.js**: 18+ (用于前端本地开发与单元测试套件)
- **FFmpeg**: 6.0+ (必须包含 `ffmpeg`, `ffprobe` 并配置于系统 PATH)
- **浏览器**: Chromium / Chrome 最新版 (已集成至 Codex in-app browser)

---

## 四、服务启动与访问指南
1. **启动 8088 主服务**:
   ```powershell
   python -m uvicorn video_farm.web:app --host 127.0.0.1 --port 8088 --log-level info
   ```
2. **访问 MuseFlow Studio 工作台**:
   - 网页入口：`http://127.0.0.1:8088/museflow`
   - 独立工作流：`http://127.0.0.1:8088/static/museflow/app.html`

---

## 五、数据备份与恢复指南
1. **工程备份**:
   - 在工作台镜头表弹窗中点击【导出完整工程归档】，下载包含全部素材与时间线元数据的 ZIP 文件；
   - 或直接备份服务端工程目录：`video_farm_data/museflow_projects/`。
2. **工程恢复**:
   - 将 ZIP 解压至任意工作目录，或调用 `ShotManager.fromJSON(projectData)` 恢复全部分镜与时间线配置。

---

## 六、已知限制与注意事项
1. **云端外部依赖**:
   - 视频生成功能依赖外部 Google Flow / Gemini / Vids 平台服务与账号登录状态。若网络不稳定可能触发重试。
2. **Gemini 网页端时长**:
   - Gemini 网页端时长由平台服务端默认决定（约 10s），不可通过前端滑块强行指定。
3. **离线模式边界**:
   - 离线环境可完整浏览工程、审片、剪辑、调序与重新导出成片，但无法发起新的 AI 云端生成任务。

---

## 七、版本回滚指引 (Rollback Instructions)
若生产环境出现非预期回归，可执行以下命令安全回滚：
```powershell
git checkout 5a4bdeb
git restore --staged .
git restore .
```
