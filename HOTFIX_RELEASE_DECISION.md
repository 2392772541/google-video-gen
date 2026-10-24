# MuseFlow Studio · Hotfix 发布与维护决策

## 一、决策结论
- **基线版本**: 保持 `museflow-studio-v0.11.0-rc2` 稳定冻结，不强制覆盖历史稳定标签；
- **Hotfix 变更**: 覆盖无限画布前端 `project.tsx`（单图放行）、`canvas-camera-movement-popover.tsx`（运镜入框编辑）及后端 `video_farm/worker.py`（时长透传与结构化错误）；
- **生产就绪度**: `PRODUCTION_READY`；
- **执行原则**: 遵照 ChatGPT 终审指示，测试结束即停机，退出主动循环。
