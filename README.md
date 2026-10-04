# 🎬 谷歌视频生成 (Google Video Gen / Video Farm)

本地视频生成调度平台。专为 **Google Flow (9:16 首尾帧刚性插值生成)** 与 **Gemini 网页版 (对话式/参考图生视频)** 设计，支持多 Google 账号并发轮换、额度熔断自动换号、逐帧刚性视觉质检以及可视化 Web 控制台与 RESTful API。

同时已注册为 Codex 本地系统技能 **`google-video-gen`**（中文唤醒名：**谷歌视频生成**），支持跨窗口随时唤起。

---

## 唤醒口令与使用方式

### 1. Codex 跨窗口召唤 (已注册技能 `google-video-gen`)
在任意 Codex 新窗口或任务中，直接输入以下内容即可自动唤起本技能：
- **中文自然语言**：
  > “帮我调用**谷歌视频生成**”  
  > “用**谷歌视频生成**做一段 9:16 首尾帧视频”  
  > “检查**谷歌视频生成**的账号状态与任务列表”
- **符号精准调用**：
  > `$google-video-gen 提交视频生成任务`  
  > `$google-video-gen 查看当前任务列表`

### 2. 本地独立 Web 控制台 (脱离 AI 独立使用)
- 双击根目录下的 **`启动视频工坊.bat`**
- 浏览器自动打开：👉 **`http://127.0.0.1:8088/`**
- 可在网页中直接进行账号登录/续期、拖拽上传图片提交任务、在线播放视频与查看 OpenCV 质检图。

---

## 🌟 核心特性

### 1. 双生成引擎架构
- **Google Flow 引擎 (`flow`)**：
  - 调用底层 `gflow-cli`（PR #831 增强版），实现真正的 **首帧图片 + 尾帧图片 + 提示词 -> 9:16 竖屏视频** 插值约束生成。
  - 自动识别并关闭 Google Flow 可见水印（Visible Watermark），保持原始纯净画面。
- **Gemini 网页版引擎 (`gemini_web`)**：
  - 基于真实 Chrome 与 Playwright 驱动 `gemini.google.com` 官方网页端。
  - 模拟真实用户交互，支持输入提示词与单/多参考图生成视频。

### 2. 多账号并发调度与自动容灾换号 (Failover)
- **账号完全沙箱隔离**：每个 Google 账号分配独立的本地 Chrome Profile 目录，彻底杜绝凭证串扰与封号风险。
- **零 Cookie 泄露安全原则**：不提取 Cookie、不上传第三方服务器，仅在本机原生 Chrome 中进行安全身份认证。
- **智能错误捕获与自动熔断**：
  - 精准识别 `QUOTA_EXHAUSTED`（额度耗尽）、`AUTH_EXPIRED`（Session到期）、`RATE_LIMITED`（频控触发）等异常。
  - 异常账号自动进入冷却挂起状态，避免频繁请求触发风控。
- **任务物理级解绑与无损接力**：
  - 账号额度用尽或异常时，当前任务状态原子化回退为 `queued`，并清空绑定账号（`assigned_profile_id = NULL`）。
  - 调度器将在下一次调度轮询中自动指派池内空闲的健康账号接续执行，实现无感自动切换。

### 3. OpenCV 自动化视觉刚性质检 (QA)
- 视频生成后自动下载原片，调用 OpenCV 提取视频物理第一帧与物理最后一帧。
- 计算首帧/尾帧与原图的 **NCC (归一化互相关系数)** 与 **SSIM (结构相似度)**。
- 自动生成对比拼接图与量化指标，杜绝“接受了尾帧但未实际约束”的假象。

### 4. 现代化 Web 管理控制台 & RESTful API
- **可视化控制台**：运行于 `http://127.0.0.1:8088/`，提供直观的账号卡片、一键原生拉起登录/续期、任务排队监控、在线播放与 QA 报告预览。
- **开放 API**：全功能 RESTful 接口，方便外部 AI Agent、自动化工作流或 Python 脚本随时投递任务与查询进度。

---

## 📂 项目结构

```text
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
├── skills/                      # Codex 技能配置目录
│   └── google-video-gen/        # 谷歌视频生成技能定义
│       └── SKILL.md             # 技能元数据与提示词指南
├── 启动视频工坊.bat              # Windows 一键启动脚本
├── verify_frames.py             # 独立抽帧验证与比对工具
├── example_shots.json           # 示例分镜任务导入文件
├── start.png                    # 测试首帧图片 (9:16)
├── end.png                      # 测试尾帧图片 (9:16)
└── .gitignore                   # 严格的安全过滤规则（防泄露凭据与大文件）
```

---

## 🚀 快速上手

### 1. 环境准备
- Windows 10/11
- Python 3.10+
- Google Chrome 浏览器
- 核心依赖：`fastapi`, `uvicorn`, `opencv-python`, `numpy`, `playwright` 等（已集成于虚拟环境中）

### 2. 一键启动
直接双击运行根目录下的：
```cmd
启动视频工坊.bat
```
终端将自动启动调度后台并拉起默认浏览器访问：
👉 **http://127.0.0.1:8088**

或使用命令行手动启动：
```bash
python -m video_farm.web --port 8088
```

---


---

## 💻 新电脑跨机迁移与复用指南 (跨电脑 100% 开箱即用)

如果你需要把本项目复制或克隆到另一台新的 Windows 电脑上使用，只需按照以下步骤操作：

### 步骤 1：复制代码到新电脑
- 通过 Git 克隆或使用 U 盘/压缩包完整拷贝本工程目录（如放置在 `D:\AI\视频制作` 或任意你喜欢的英文路径）。

### 步骤 2：一键配置运行环境（双击即装）
- 打开项目根目录，双击运行：
  ```cmd
  一键配置环境.bat
  ```
  该脚本会自动：
  1. 检查 Python 3.10+ 环境。
  2. 自动创建本地隔离的虚拟环境 `.venv`。
  3. 自动安装 `requirements.txt` 中全部依赖（FastAPI, OpenCV, Playwright, Edge-TTS 等）。
  4. 自动初始化 Playwright 浏览器内核。
  5. 自动检查并补齐 `gflow-cli` 首尾帧插值引擎。
  6. 检查系统 `ffmpeg`（音视频母带合成必需）。

### 步骤 3：注册 Codex 技能（可选）
- 如果新电脑上也安装了 Codex 并希望支持跨窗口召唤，双击运行：
  ```cmd
  注册本地技能.bat
  ```
  技能将自动安装到 `%USERPROFILE%\.codex\skills\google-video-gen`，随时输入“谷歌视频生成”即可唤醒。

### 步骤 4：一键启动管理后台
- 双击运行根目录下的：
  ```cmd
  启动视频工坊.bat
  ```
- 浏览器将自动打开：👉 **`http://127.0.0.1:8088/`**

### 步骤 5：新电脑添加第一个 Google 账号
1. 在 Web 控制台左侧点击 **【+ 注册/绑定新 Profile】**（例如起名为 `acc1`）。
2. 点击卡片上的 **【🚀 弹出 Chrome 登录/续期】** 按钮。
3. 在弹出的真实 Chrome 窗口中正常登录你的 Google 账号，登录成功后直接关闭该 Chrome 窗口。
4. 回到网页点击 **【🔍 检查/刷新】**，状态变为 `idle` 绿色就绪即可开始批量生产视频！

## 🔌 API 接口概览

本系统提供标准 RESTful API，便于外部系统与 AI Agent 调用：

| 接口 | 方法 | 说明 |
|---|---|---|
| `/api/status` | GET | 查询调度器运行状态、排队任务数、就绪账号数 |
| `/api/profiles` | GET / POST | 列出或注册 Chrome 账号 Profile |
| `/api/profiles/{id}/launch` | POST | 弹出真实 Chrome 窗口供人工登录或免密续期 |
| `/api/profiles/{id}/status` | POST | 手动切换账号状态（如暂停 `paused` 或就绪 `idle`） |
| `/api/tasks` | GET / POST | 查询任务列表或创建单个视频任务 |
| `/api/tasks/batch` | POST | 批量提交多个视频生成任务 |
| `/api/tasks/{id}/cancel` | POST | 取消等待中的任务 |
| `/api/tasks/{id}/logs` | GET | 实时读取特定任务的执行日志流 |

---

## 🛡️ 安全与风控合规守则

1. **独立用户目录**：每个账号拥有完全独立的 Profile 路径，绝对不共用本地缓存，不与用户日常主力 Chrome 冲突。
2. **物理单并发限制**：同一个 Chrome Profile 同时仅允许执行一个生成任务，避免同一 Profile 的并发操作冲突；不保证账号不会被上游限制。
3. **不触碰灰色机制**：不做代理池 IP 伪造、不做指纹虚标欺骗，遵循真实浏览器正常交互逻辑。
4. **Git 敏感资产保护**：`.gitignore` 默认已排除全部运行时数据目录 `video_farm_data/`、数据库 `*.db`、生成视频 `*.mp4` 以及任何可能包含 Session 的 `*profile*` 目录。


## 2026-10-02 本地维护与验收补充

- 服务保持单入口 `http://127.0.0.1:8088/`。Host/同源校验用于降低浏览器跨站请求和 DNS rebinding 风险，**不是完整的用户身份鉴权**；不要把此服务直接暴露到公网或不可信局域网，不要绕过校验反向代理发布。
- 主任务列表使用 `limit` / `offset` 分页，`limit` 最大 500；响应仍为数组，总数见 `X-Total-Count`。概览是全库统计，分类与批量勾选仅限当前页。
- 正在执行的任务不允许删除。普通删除会隔离未共享的管理目录产物并保存恢复清单，保留输入素材、外部文件和共享产物；不要自行清空 `video_farm_data/trash/`。
- 只读巡检（在项目根目录运行）：
  ```powershell
  & 'E:\app\Miniconda\python.exe' -m video_farm.maintenance --output '.\qa_output\maintenance-latest.json'
  ```
- 隔离恢复先预览，再决定是否应用；将下例路径替换成真实删除清单路径，不要凭空创建清单：
  ```powershell
  & 'E:\app\Miniconda\python.exe' -m video_farm.maintenance --restore '<真实 manifest.json 的绝对路径>'
  # 阅读预览，确认没有覆盖和路径冲突后，才使用：
  & 'E:\app\Miniconda\python.exe' -m video_farm.maintenance --restore '<真实 manifest.json 的绝对路径>' --apply
  ```
  恢复不会覆盖现有任务/文件；等待中的任务恢复为取消状态，需明确重试才会继续生成。建议先暂停提交新任务并确认没有执行中的任务。
- Timeline/Pipeline 本地合成使用 1 个 worker，最多接收 4 个未完成作业（含执行中作业），检查至少 2GiB 可用内存，FFmpeg 解码/滤镜/输出各限制为 2 线程。**这些不是整个系统所有 Chrome/FFmpeg 任务的全局资源限额**；大规模生产仍需观察内存、磁盘和其他任务。
- 缺少素材、外部 TTS 依赖或不可兼容的上游请求应明确报错，不能把黑屏文件或可点击按钮作为成功证据。模型、账号登录、额度、上游网页/API 是否可用，必须通过相应真实任务验收。
- 不要因为根目录出现空数据库文件就删除数据库；当前任务库路径可由只读巡检输出核实。不要用旧备份直接覆盖新数据。
- 本轮完整审查、验收证据及回滚说明见 `qa_output/system-audit-20261002-205008/`。历史快照中的数量和运行 PID 不代表未来状态。
