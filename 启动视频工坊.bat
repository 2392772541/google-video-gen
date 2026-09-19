@echo off
chcp 65001 >nul
title Video Farm 视频工坊 · 控制台
cls

echo ============================================================
echo   🎬 Video Farm 视频工坊 · 本地管理控制台
echo   Google Flow 9:16/16:9 首尾帧生成与多账号智能调度平台
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

echo [1/2] 正在启动后台调度引擎与 Web 服务 (端口: 8088)...
echo 使用 Python: %PY_EXE%
start "" http://127.0.0.1:8088

echo [2/2] 服务已启动，正在监听 http://127.0.0.1:8088
echo 提示：关闭此窗口即可停止服务。按 Ctrl+C 可优雅退出。
echo.

"%PY_EXE%" -m video_farm.web --port 8088

pause
