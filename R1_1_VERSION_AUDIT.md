# MuseFlow Studio 版本审计与标签冻结说明书 (R1.1 阶段)

## 一、Git 版本基准与标签审计 (Version Audit)

- **旧 RC 标签**: `museflow-studio-v0.11.0-rc1` (指向 Commit `cd890b1`，未包含 `blur_pad` 商业级虚化背景滤镜)；
- **新特性增量**:
  - `video_farm/timeline_assembler.py`: 新增 `aspect_mode="blur_pad"` 高斯环境散焦背景填充功能；
  - `PROJECT_B_YOUGEN_PRODUCT_PROMO.json`: 显式固化 `timelineConfig.aspectMode = "blur_pad"`；
  - 10 关键帧正式 40 秒视频物理抽样与校验；
  - 独立沙箱目录成片重导出 100% 通过；
- **版本冻结策略**:
  - 严格遵守“不得覆盖或移动已有历史发布标签”的准则；
  - 正式创建新的发布候选标签：**`museflow-studio-v0.11.0-rc2`** 并推送到远端仓库；
  - 当真实业务人员在 `R1_HUMAN_REVIEW_RECORDS.md` 中签署确认后，再行签发正式稳定版标签 `museflow-studio-v0.11.0`。

---

## 二、运行依赖与环境参数

1. **核心环境要求**:
   - Python: 3.10+
   - FFmpeg: 6.0+ (支持 libx264, aac, boxblur, complex_filter)
   - Node.js: 18+ (无限画布运行环境)
2. **服务端口与健康状态**:
   - 8088: 视频工坊核心调度服务 (`video_farm`) ➔ 健康运行中
   - 3000: 无限画布前端 UI ➔ 健康运行中
   - 8317: 统一网关 (`gateway`) ➔ 健康运行中
3. **启动与停止命令**:
   - 启动工坊: `python run_farm.py` (常驻后台)
   - 启动画布: `npm run dev` (在前端目录)
   - 停止服务: 采用常规 SIGINT 优雅退出，严禁强杀以防止对账缓存损坏。

---

## 三、发布候选标签冻结记录

- **Git 标签名称**: `museflow-studio-v0.11.0-rc2`
- **版本类型**: Release Candidate (发布候选版 2)
- **当前发布裁决**: `RELEASE_CANDIDATE_PENDING` (待人工终审签发)
