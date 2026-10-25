@echo off
chcp 65001 >nul
title Video Farm 视频工坊 · 控制台
cls

echo ============================================================
echo   🎬 Video Farm 视频工坊 · 本地管理控制台
echo   Google Vids 创作工作台 · 独立平台选择与多账号调度
echo ============================================================
echo.

cd /d "%~dp0"

:: 优先检测当前项目的 .venv
set "PY_EXE="
if exist ".venv\Scripts\python.exe" (
    set "PY_EXE=.venv\Scripts\python.exe"
) else if exist "gflow-cli\.venv\Scripts\python.exe" (
    set "PY_EXE=gflow-cli\.venv\Scripts\python.exe"
) else (
    set "PY_EXE=python"
)

:: 检查 Python 是否可用
"%PY_EXE%" --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [提示] 未检测到有效的 Python 环境，请先双击运行【一键配置环境.bat】！
    pause
    exit /b 1
)

echo [1/3] 正在自启动无限画布前端 (3000) 与代理服务 (23210)...
"%PY_EXE%" -c "from video_farm.canvas_autostart import ensure_canvas_services; ensure_canvas_services()" >nul 2>&1

echo [2/3] 正在启动后台调度引擎与 Web 服务 (端口: 8088)...
echo 使用 Python: %PY_EXE%

echo [3/3] 正在加载服务，请等到下方出现 Uvicorn running 后再打开页面。
echo 页面地址：http://127.0.0.1:8088/canvas (无限画布)
echo 页面地址：http://127.0.0.1:8088/vids (Google Vids)
echo 提示：关闭此窗口即可停止服务。按 Ctrl+C 可优雅退出。
echo.

"%PY_EXE%" -m video_farm.web --port 8088

pause
