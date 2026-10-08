# 🎬 谷歌视频生成 (Google Video Gen / Video Farm)

本地视频制作工作台，主入口是 **Google Vids**；Google Flow 与 Gemini 是独立可选平台，不是 Vids 的替代实现。支持分镜 JSON、素材预检、账号池调度、任务进度、停止、结果预览与下载。上游模型、登录、额度及生成耗时仍取决于对应平台，不保证每个账号或每次请求成功。

## 快速启动

1. Windows 10/11，安装 Python 3.10+、项目依赖与 Google Chrome；媒体检验/合成需要 FFmpeg/ffprobe。
2. 双击根目录的 **`启动视频工坊.bat`**。首次配置可以使用 **`一键配置环境.bat`**，随后检查依赖安装结果；迁移到新电脑仍需重新登录和真实验收。
3. **等终端出现 `Uvicorn running` 后，手动打开** [Google Vids 工作台](http://127.0.0.1:8088/vids)。启动器不会自动打开浏览器。
4. [主控制台](http://127.0.0.1:8088/) 提供账号、全部任务和独立的生图/配音等入口。关闭终端会停止服务；建议在原服务终端按 `Ctrl+C` 优雅退出。

也可以在项目根目录用已安装依赖的 Python 执行：

```powershell
python -m video_farm.web --port 8088
```

Python 文件修改后需要退出并重新启动原服务，刷新网页不会重新加载后端。不要重复启动多个 8088 服务，不要为了加载修改强杀浏览器或覆盖任务库。

## 平台和规格边界

| 平台 / 引擎值 | 当前接入方式 | 重要限制 |
|---|---|---|
| **Google Vids / `vids`** | `docs.google.com/videos` 的真实编辑器；文生视频、单图动画 | Omni，720p 或 1080p；16:9 或 9:16；3–10 秒。**当前适配器没有尾帧绑定能力** |
| Google Flow / `flow` | 独立 `gflow-cli` 驱动 | 首尾帧必须成对提供；可用模型/规格以对应平台实际接入结果为准，不保证刚性插值 |
| Gemini / `gemini` | `gemini.google.com` 官方网页 | 使用独立入口和账号会话；当前适配器不接受尾帧绑定，不保证所有账号都能生视频 |

- Google Vids 请求不会暗中转到 Flow/Gemini，不会把首尾帧请求降成仅首帧。当前无法执行的请求在提交前明确失败。
- **此处描述的是本项目适配器能力，不是对 Google Vids 平台永久能力的判断。** 若需要 Vids 双帧支持，必须先实现实际绑定并验证，不能只改 `engine` 字符串。
- 输出完成前检查实际成片尺寸、画幅和时长；不匹配的文件不标记成功。提示词写“1080p”本身不等于选择了 1080p。
- Google Vids 工程 URL 可留空，执行时创建新工程；只有用户明确提供地址才绑定既有工程，不内置私人文档 URL。

## 分镜与 JSON 批量导入

1. 在 `/vids` 新建或选中工作流，选择平台、模型/画质、画幅和时长。
2. 上传/选择可解码图片，或在 JSON 中填写真实可读的本地素材路径。跨电脑复制代码不会自动迁移这些素材。
3. 粘贴 JSON 或选择 JSON 文件，预览镜头、平台及图片。不要仅看到导入成功就认为已生成。
4. 当前导入 API 的 `auto_start` 缺省为 `true`；**只保存草稿必须显式传 `auto_start: false`**。需要启动时，整批先预检通过才会原子化入队；不会留下半批任务。前端提交值以实际“导入并生成/保存草稿”操作为准。
5. 不指定账号时每个镜头由健康空闲账号池动态调度；只有明确选择账号才固定绑定。没有可用账号时会等待并显示原因，不代表生成服务已开始。
6. 真实单图 Vids 样例可从工作台/API 获取；首尾双帧素材应保留，不要删除尾帧来伪装为兼容。只有用户明确选择 Flow，才走 Flow 双帧生成。

常用字段包含 `engine`、`model`、`resolution`、`aspect_ratio`、`doc_url` 和 `shots`；每个镜头可设置 `prompt`、`duration`、`image_url`、`end_image_url`。用 [样例接口](http://127.0.0.1:8088/api/vids/sample_import_json) 或导出 JSON 核对实际格式。导入预检与真实上游生成是两个验收层级。

## 账号、停止与失败恢复

- 每个账号使用独立 Chrome Profile；同一 Profile 同时只允许一个生成/登录操作。独立目录降低串扰风险，**不保证账号不会被上游限制**。
- 在主控制台注册账号并打开登录窗口，手动完成登录。登录/检查时不抢占正在生成的 Profile，不提取或提交 Cookie。
- 排队/等待重试的任务使用 **取消**；执行/调度/检验中的任务使用 **停止**。工作流支持停止未完成镜头，停止后需等执行器退出确认并释放账号；清理失败会隔离账号，不直接借给下一个任务。
- 停止本地执行**不保证云端任务已取消或额度退回**。避免停止后立刻重复提交同一未知请求。
- 对可确认尚未提交的错误可重试/切换账号；对已提交但结果无法确认的情况保留未知状态和证据，**不自动重发**。应先在原平台核对产物，再决定恢复或重试。
- 检查任务阶段、最近日志、账号状态和输出证据，区分排队、页面操作、上游生成、下载及验证。上游生成可能持续数分钟，本地排队/超时也会增加总耗时；不作固定时间或提速倍数保证。

## 结果与视觉检验

完成任务可在工作台播放器预览、下载单个视频或工作流 ZIP。只有实际文件存在且规格通过才作为完成依据。Flow 双帧任务可提取首尾帧并计算 NCC/SSIM 对比；这些指标是检查证据，不保证生成画面严格相等。

## 主要 API

以运行服务的 [OpenAPI 文档](http://127.0.0.1:8088/docs) 为准；以下不是全部接口：

| 接口 | 方法 | 用途 |
|---|---|---|
| `/api/overview` | GET | 调度/任务/账号概览 |
| `/api/profiles` | GET | 账号列表 |
| `/api/profiles/add` | POST | 注册账号 |
| `/api/profiles/{id}/launch-login` | POST | 打开人工登录窗口 |
| `/api/tasks` | GET | 分页查询任务 |
| `/api/tasks/create` | POST | 创建单个任务 |
| `/api/tasks/batch` | POST | 批量创建视频任务 |
| `/api/tasks/{id}/cancel` | POST | 取消等待任务 |
| `/api/tasks/{id}/stop` | POST | 停止执行任务 |
| `/api/tasks/{id}/retry` | POST | 显式重试允许重试的任务 |
| `/api/tasks/{id}/download` | GET | 下载任务产物 |
| `/api/vids/overview` | GET | Vids 工作流概览 |
| `/api/vids/batch_import` | POST | JSON 预检、草稿保存或批量入队 |
| `/api/vids/shots/{id}/generate` | POST | 生成单镜头 |
| `/api/vids/workflows/{id}/generate_all` | POST | 生成工作流待执行镜头 |
| `/api/vids/workflows/{id}/stop_all` | POST | 停止工作流未完成镜头 |
| `/api/vids/workflows/{id}/package_zip` | GET | 导出工作流素材包 |

## 项目结构与测试

- `video_farm/web.py`：FastAPI 主服务；`vids_router.py` / `vids_workflow.py`：分镜与导入。
- `scheduler.py` / `db.py` / `execution_control.py`：调度、原子状态及执行归属。
- `vids_worker.py` / `worker.py` / `gemini_worker.py`：三个不同平台；`video_contract.py`：视频请求预检。
- `image_worker.py` / `image_web_runner.py`：独立生图执行；`verify.py`：媒体视觉检验。
- `video_farm/static/`：实际前端；`video_farm/tests/`：Python 与 Node 回归测试。
- `video_farm_data/`：本机任务库、Profile 和产物，不纳入 Git。

串行运行隔离测试，避免影响生产队列：

```powershell
python -m pytest video_farm/tests/ -q
Get-ChildItem video_farm/tests/*.cjs | ForEach-Object { node --test $_.FullName; if ($LASTEXITCODE) { throw '前端回归失败' } }
python run_e2e_verification.py
```

`run_e2e_verification.py` **仅做只读 HTTP smoke**，不创建/停止/生成任务，不等于端到端生成验收。隔离测试默认禁止生产调度器、浏览器、子进程和网络副作用；`VIDEO_FARM_LIVE_E2E=1` 才启用只读现场测试。发布验收还要在重启后的实际应用中验证：入队、调度、指定平台、真实产物规格、播放器、下载和停止/取消；原生 Google 网页成功不能替代本应用完整链路。

## 安全、迁移与备份

- 服务仅供本机使用；Host/同源校验不是用户登录鉴权，不要公开到公网或不可信局域网。
- Git 备份只提交源码、测试和文档，不提交任务库、Cookie、Profile、媒体或本地验收截图。运行数据如需备份应单独妥善保存，不能用旧库覆盖新任务。
- 新电脑安装依赖后，重新添加/登录账号并迁移需要的素材；`gflow-cli` 等被忽略的独立子系统需自行配置并验证。
- 可选运行 `注册本地技能.bat` 安装 `google-video-gen`，技能的旧说明不能覆盖用户实际选择的平台。

---

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
