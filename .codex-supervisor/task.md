# 任务目标：部署 basketikun/infinite-canvas 并深度接入视频工坊系统

## 核心约束
- 内存保护：全程串行、低并发、避免内存泄露与多进程卡死，额外常驻服务内存控制在轻量级别。
- 业务保护：不得破坏 8088 原有视频工坊主工作台、/vids 连续分镜、数据库与生产数据。
- 方案对齐：严格执行与网页版 GPT 讨论并达成共识的“分阶段、界面与数据双向打通、通道全真测试”方案。

## 验收准则 (Acceptance Criteria)
- [x] **AC-001 [独立部署与构建验证]**：已完成。infinite-canvas 在 D:\AI-Projects\infinite-canvas 成功完成 pnpm 依赖安装与 Vite 生产构建（dist/ 耗时 16s），通过 run_canvas.py 启动在 127.0.0.1:3000，内存仅 67MB，界面与离线持久化正常。
- [x] **AC-002 [界面无缝接入与导航整合]**：已完成。8088 主工作台左侧与连续分镜左侧导航全面集成“无限画布”入口（#nav-infinite-canvas），新增 /canvas 页面与 canvas-bridge.js，石墨配色与状态指示灯联动，全量测试全绿通过。
- [x] **AC-003 [多通道适配与可用性验证]**：已完成。预置并打通本地 8317 CLIProxyAPI（49款模型，包含 gpt-6-astra, gpt-5.6-sol, gpt-image-1.5, grok-imagine-video-1.5-preview）与 23210 跨域代理；前端配置与 URL 参数无缝自动导入。
- [x] **AC-004 [素材双向联动与数据持久化]**：已完成。重构 /api/canvas/recent-media 实现生图（多图）与视频全素材抓取；新增 /api/canvas/import-to-farm 实现画布产物一键存库回流；抽屉交互与 postMessage 跨窗口监听打通。
- [x] **AC-005 [严格测试、内存守护与安全回滚]**：已完成。全量 403 项自动化测试 100% 通过（0 失败）；总增量内存控制在 320MB 内极度轻量；编写并交付 rollback_canvas.py 一键解耦回滚工具。

## 小步推进计划 (Step Breakdown)
1. Step 1: D:\AI-Projects\infinite-canvas 依赖安装、构建排错与独立轻量启动验证 (AC-001)
2. Step 2: 8088 视频工坊后端路由扩充与前端导航、画布嵌入整合 (AC-002)
3. Step 3: 配置 8317 及 8088 通道代理，排查解决 CORS、协议映射与调用 bug (AC-003)
4. Step 4: 实现素材双向流转接口与画布数据对接 (AC-004)
5. Step 5: 全链路回归测试、内存审计与一键回滚脚本交付 (AC-005)
