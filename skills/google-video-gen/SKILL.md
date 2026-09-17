---
name: google-video-gen
description: 谷歌视频生成（Google Video Gen / 视频工坊）。用于 Google Flow 9:16 首尾帧刚性插值生视频、Gemini 网页版视频生成、多 Google 账号调度、自动熔断换号与质检。当用户输入“谷歌视频生成”、“首尾帧生视频”、“谷歌视频”、“视频工坊”、“google-video-gen”或需要进行谷歌平台视频生成时调用。
metadata:
  short-description: 谷歌视频生成与多账号调度系统
---

# 谷歌视频生成 (Google Video Gen)

本技能用于在任何 Codex 对话窗口或任务中调度与管理本地 **谷歌视频生成系统（Video Farm）**。
系统支持 **Google Flow (9:16 首尾帧刚性约束)** 与 **Gemini 网页版 (对话/参考图)** 双引擎，并具备多账号沙箱隔离、自动熔断与无感换号能力。

---

## 唤醒口令与触发方式

在任何 Codex 窗口中，可通过以下方式直接唤起本技能：
1. **自然语言直接召唤**：
   - “帮我调用**谷歌视频生成**”
   - “用**谷歌视频生成**做一段首尾帧视频”
   - “检查**谷歌视频生成**的账号与任务状态”
2. **符号精准触发**：
   - `$google-video-gen 提交视频生成任务`
   - `$google-video-gen 查看当前任务列表`

---

## 📍 本地系统位置与入口

- **工作区根目录**：`C:\Users\win10\Documents\ChatGPT\视频制作`
- **一键双击启动**：`C:\Users\win10\Documents\ChatGPT\视频制作\启动视频工坊.bat`
- **Web 可视化控制台**：`http://127.0.0.1:8088/`
- **Python 环境**：`C:\Users\win10\Documents\ChatGPT\视频制作\gflow-cli\.venv\Scripts\python.exe`（或系统 Python）

---

## 🚀 常用操作指令 (跨窗口调用)

### 1. 检查后台服务与账号状态 (REST API 优先)

在任何会话中执行以下命令查询调度器状态：
```powershell
curl.exe -s http://127.0.0.1:8088/api/status
```
如果服务未启动，可直接后台静默拉起：
```powershell
cd "C:\Users\win10\Documents\ChatGPT\视频制作"
Start-Process -FilePath "启动视频工坊.bat" -WindowStyle Hidden
```

### 2. 查询当前可用账号池 (Profiles)
```powershell
curl.exe -s http://127.0.0.1:8088/api/profiles
```
返回各账号 Profile 的状态（`idle` 空闲可用、`busy` 执行中、`cooldown` 熔断冷却、`paused` 暂停）。

### 3. 提交生成任务

#### A. 提交 Google Flow 9:16 首尾帧任务
```powershell
curl.exe -s -X POST http://127.0.0.1:8088/api/tasks `
  -H "Content-Type: application/json" `
  -d '{
    "engine": "flow",
    "prompt": "保持主体一致，镜头自然平滑过渡至尾帧状态",
    "start_frame_path": "C:/Users/win10/Documents/ChatGPT/视频制作/start.png",
    "end_frame_path": "C:/Users/win10/Documents/ChatGPT/视频制作/end.png",
    "aspect_ratio": "9:16",
    "duration_sec": 8,
    "priority": 10
  }'
```

#### B. 提交 Gemini 网页版对话生视频任务
```powershell
curl.exe -s -X POST http://127.0.0.1:8088/api/tasks `
  -H "Content-Type: application/json" `
  -d '{
    "engine": "gemini_web",
    "prompt": "生成一段阳光照耀下雨滴滴落水面的高清慢动作视频",
    "aspect_ratio": "16:9",
    "duration_sec": 8,
    "priority": 10
  }'
```

### 4. 任务进度追踪与质检报告读取
```powershell
# 查询任务列表与实时状态
curl.exe -s http://127.0.0.1:8088/api/tasks

# 查看指定任务的详细日志
curl.exe -s http://127.0.0.1:8088/api/tasks/<task_id>/logs
```
当任务状态变为 `success` 时，返回结果包含：
- `output_video_path`：无水印高清 MP4 文件的本地绝对路径。
- `qa_passed`：OpenCV 物理首尾帧与原图的相似度质检结果（NCC / SSIM）。
- `qa_report`：量化质检分值与对比详情。

---

## 🛠️ CLI 命令行操作备忘 (备用)

无需打开 Web 服务时，可直接在工作区通过 CLI 运行：
```powershell
cd "C:\Users\win10\Documents\ChatGPT\视频制作"

# 查看任务
python -m video_farm.cli task list

# 提交任务
python -m video_farm.cli task add "提示词" --start start.png --end end.png --aspect 9:16

# 查看任务与质检详情
python -m video_farm.cli task show <task_id>
```

---

## 🛡️ 安全合规规则
1. **沙箱隔离**：各 Google 账号使用独立 Chrome Profile 运行，互不干扰。
2. **零凭据泄露**：绝对不导出、不提取、不上传 Google Cookie 或登录凭据。
3. **熔断换号**：单账号额度耗尽时自动移入冷却队列，由其他可用账号无损接替任务。
