# 🎬 Video Farm (视频工坊) - Google Flow & Gemini 双引擎多账号调度系统

Video Farm 是一个轻量、稳定且高可用的本地视频生成调度平台。专为 **Google Flow (9:16 首尾帧刚性插值生成)** 与 **Gemini 网页版 (对话式/参考图生视频)** 设计，支持多 Google 账号并发轮换、额度熔断自动无缝换号、逐帧刚性视觉质检以及可视化 Web 管理控制台与 RESTful API。

---

## 🌟 核心特性

### 1. 双生成引擎架构
- **Google Flow 引擎 (low)**：
  - 调用底层 gflow-cli（PR #831 增强版），实现真正的 **首帧图片 + 尾帧图片 + 提示词 -> 9:16 竖屏视频** 插值约束生成。
  - 自动识别并关闭 Google Flow 可见水印（Visible Watermark），保持原始纯净画面。
- **Gemini 网页版引擎 (gemini_web)**：
  - 基于真实 Chrome 与 Playwright 驱动 gemini.google.com 官方网页端。
  - 模拟真实用户交互，支持输入提示词与单/多参考图生成视频。

### 2. 多账号并发调度与自动容灾换号 (Failover)
- **账号完全沙箱隔离**：每个 Google 账号分配独立的本地 Chrome Profile 目录，彻底杜绝凭证串扰与封号风险。
- **零 Cookie 泄露安全原则**：不提取 Cookie、不上传第三方服务器，仅在本机原生 Chrome 中进行安全身份认证。
- **智能错误捕获与自动熔断**：
  - 精准识别 QUOTA_EXHAUSTED（额度耗尽）、AUTH_EXPIRED（Session到期）、RATE_LIMITED（频控触发）等异常。
  - 异常账号自动进入冷却挂起状态，避免频繁请求触发风控。
- **任务物理级解绑与无损接力**：
  - 账号额度用尽或异常时，当前任务状态原子化回退为 queued，并清空绑定账号（ssigned_profile_id = NULL）。
  - 调度器将在下一次调度轮询中自动指派池内空闲的健康账号接续执行，实现无感自动切换。

### 3. OpenCV 自动化视觉刚性质检 (QA)
- 视频生成后自动下载原片，调用 OpenCV 提取视频物理第一帧与物理最后一帧。
- 计算首帧/尾帧与原图的 **NCC (归一化互相关系数)** 与 **SSIM (结构相似度)**。
- 自动生成对比拼接图与量化指标，杜绝“接受了尾帧但未实际约束”的假象。

### 4. 现代化 Web 管理控制台 & RESTful API
- **可视化控制台**：运行于 http://127.0.0.1:8088/，提供直观的账号卡片、一键原生拉起登录/续期、任务排队监控、在线播放与 QA 报告预览。
- **开放 API**：全功能 RESTful 接口，方便外部 AI Agent、自动化工作流或 Python 脚本随时投递任务与查询进度。

---

## 📂 项目结构

`	ext
视频制作/
├── video_farm/                  # 核心系统包
│   ├── __init__.py
│   ├── __main__.py              # 模块入口 (python -m video_farm)
│   ├── db.py                    # SQLite 状态机与任务管理、解绑换号逻辑
│   ├── models.py                # 强类型数据模型 (Task, Profile, EngineType 等)
│   ├── scheduler.py             # 核心调度器：并发控制、熔断捕获与自动 Failover
│   ├── worker.py                # Google Flow 首尾帧生视频驱动
│   ├── gemini_worker.py         # Gemini 网页版 Playwright 自动化驱动
│   ├── verify.py                # OpenCV 双帧刚性质检引擎 (NCC/SSIM)
│   ├── web.py                   # FastAPI 后端服务与路由
│   └── static/                  # Web 控制台前端静态资源
│       ├── index.html           # 响应式控制台页面
│       ├── style.css            # 现代化暗色主题样式
│       └── app.js               # 前端交互与实时刷新逻辑
├── 启动视频工坊.bat              # Windows 一键启动脚本
├── verify_frames.py             # 独立抽帧验证与比对工具
├── example_shots.json           # 示例分镜任务导入文件
├── start.png                    # 测试首帧图片 (9:16)
├── end.png                      # 测试尾帧图片 (9:16)
└── .gitignore                   # 严格的安全过滤规则（防泄露凭据与大文件）
`

---

## 🚀 快速上手

### 1. 环境准备
- Windows 10/11
- Python 3.10+
- Google Chrome 浏览器
- 核心依赖：astapi, uvicorn, opencv-python, 
umpy, playwright 等（已集成于虚拟环境中）

### 2. 一键启动
直接双击运行根目录下的：
`cmd
启动视频工坊.bat
`
终端将自动启动调度后台并拉起默认浏览器访问：
👉 **http://127.0.0.1:8088**

或使用命令行手动启动：
`ash
python -m video_farm.web --port 8088
`

---

## 💻 Web 控制台使用指南

1. **添加与管理账号**：
   - 在页面顶部的“账号配置与多 Profile 状态”卡片中，输入账号名称（如 low-account-01）和标识，点击**创建新 Profile**。
   - 点击该账号卡片上的**“登录”**按钮，系统将以独立沙箱用户目录弹出官方 Chrome 窗口。
   - 在弹出的窗口中正常登录 Google 账号并完成认证即可，登录状态将安全保存在本机独立目录中。
2. **提交任务**：
   - 支持选择生成引擎：Google Flow (首尾帧 9:16) 或 Gemini 网页版 (对话/参考图)。
   - 支持拖拽上传首帧与尾帧，设定视频时长与优先级。
   - 点击**提交任务**，后台调度器会自动选择空闲账号开跑。
3. **查看进度与产物**：
   - 任务列表中可实时查看状态（排队、执行中、质检、成功、失败）。
   - 点击任务可展开完整执行日志、在线视频播放器与首尾帧质检数值报告。

---

## 🔌 API 接口概览

本系统提供标准 RESTful API，便于外部系统与 AI Agent 调用：

| 接口 | 方法 | 说明 |
|---|---|---|
| /api/status | GET | 查询调度器运行状态、排队任务数、就绪账号数 |
| /api/profiles | GET / POST | 列出或注册 Chrome 账号 Profile |
| /api/profiles/{id}/launch | POST | 弹出真实 Chrome 窗口供人工登录或免密续期 |
| /api/profiles/{id}/status | POST | 手动切换账号状态（如暂停 paused 或就绪 idle） |
| /api/tasks | GET / POST | 查询任务列表或创建单个视频任务 |
| /api/tasks/batch | POST | 批量提交多个视频生成任务 |
| /api/tasks/{id}/cancel | POST | 取消等待中的任务 |
| /api/tasks/{id}/logs | GET | 实时读取特定任务的执行日志流 |

---

## 🛡️ 安全与风控合规守则

1. **独立用户目录**：每个账号拥有完全独立的 Profile 路径，绝对不共用本地缓存，不与用户日常主力 Chrome 冲突。
2. **物理单并发限制**：同一个 Chrome Profile 同时仅允许执行一个生成任务，防止并发导致 Google 封号。
3. **不触碰灰色机制**：不做代理池 IP 伪造、不做指纹虚标欺骗，遵循真实浏览器正常交互逻辑。
4. **Git 敏感资产保护**：.gitignore 默认已排除全部运行时数据目录 ideo_farm_data/、数据库 *.db、生成视频 *.mp4 以及任何可能包含 Session 的 *profile* 目录。