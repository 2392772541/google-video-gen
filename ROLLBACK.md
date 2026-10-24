# 系统回滚与安全还原方案 (ROLLBACK.md)

---

## 1. 概述与适用场景
如果在后续运行过程中出现未预期的上游接口变更、平台版本不兼容或需要恢复初始状态，可按本手册快速执行代码与配置回滚。

---

## 2. 改动模块与受影响文件清单

### 2.1 视频工坊后端 (`C:\Users\win10\Documents\ChatGPT\视频制作`)
- `video_farm/canvas_video_compat.py`（工程 ID 解耦、模型权重、120s 超时、生图转发与重试、10s 严格收敛至 omni-flash）
- `video_farm/vids_router.py`（补充 `total_workflows` 契约兼容字段）
- `video_farm/worker.py`（多图分号拆分路径解析、Veo 模型 6s 保持）
- `video_farm/vids_worker.py`（去除画布虚拟 project_id 强前缀校验，自动退回空工程）
- `video_farm/gemini_worker.py`（去除 `--disable-blink-features=AutomationControlled` 报警告参数，跳过盲匹）
- `video_farm/scheduler.py`（多图路径合法性校验与格式拆分）
- `video_farm/web.py`（多图参考校验放行与前缀挂载）

### 2.2 无限画布前端 (`D:\AI-Projects\infinite-canvas\web`)
- `web/src/pages/canvas/project.tsx`（视频生成结果即时播放回显，后台异步落盘）
- `web/src/components/canvas/canvas-top-bar.tsx`（Codex 连接状态胶囊徽章样式与标题避让）
- `web/src/lib/model-spec.ts`（支持 4s/6s/8s 时长、gpt-image-2 / 2.5 规格定义）
- `web/src/stores/use-config-store.ts`（挂载 2.0/2.5 图像模型规格与模型渠道映射）
- `web/src/services/api/image.ts`（网络/DNS 错误友好转译、双次重试逻辑）

### 2.3 代理网关与守护脚本 (`C:\Users\win10\Desktop\CLIProxyAPI_7.0.2_windows_amd64`)
- `config.yaml`（`request-retry: 3`, `max-retry-credentials: 0`, `transient-error-cooldown-seconds: 15`）
- `run-cli-proxy-api-daemon.ps1`（健康检测超时从 3s 提升至 10s，连续失败阈值从 3 次提升至 6 次）

---

## 3. 一键快速回滚指令

### 3.1 视频工坊代码回滚
```powershell
cd "C:\Users\win10\Documents\ChatGPT\视频制作"
git checkout -- video_farm/canvas_video_compat.py video_farm/vids_router.py video_farm/worker.py video_farm/vids_worker.py video_farm/gemini_worker.py video_farm/scheduler.py video_farm/web.py
```

### 3.2 无限画布代码回滚
```powershell
cd "D:\AI-Projects\infinite-canvas\web"
git checkout -- src/
npm run build
```

### 3.3 代理配置与守护进程回滚
```powershell
# 还原配置文件
Copy-Item "C:\Users\win10\Desktop\CLIProxyAPI_7.0.2_windows_amd64\config.yaml.bak-pre-antigravity-fix-20261021-162032" "C:\Users\win10\Desktop\CLIProxyAPI_7.0.2_windows_amd64\config.yaml" -Force
```

---

## 4. 服务重启指引
回滚后若需重启对应服务：
1. **视频工坊 8088**：
   ```powershell
   Stop-Process -Id (Get-NetTCPConnection -LocalPort 8088).OwningProcess -Force
   python -m uvicorn video_farm.web:app --host 127.0.0.1 --port 8088
   ```
2. **无限画布 3000**：
   ```powershell
   cd "D:\AI-Projects\infinite-canvas\web"
   npm run preview -- --port 3000 --host 0.0.0.0
   ```
