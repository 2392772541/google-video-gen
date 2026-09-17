@echo off
chcp 65001 >nul
title Video Farm 视频工坊 · 首尾帧控制台
cls

echo ============================================================
echo   🎬 Video Farm 首尾帧视频工坊 · 本地管理控制台
echo   Google Flow 9:16 首尾帧生成与多账号调度系统
echo ============================================================
echo.

cd /d "%~dp0"

set "PY_EXE=gflow-cli\.venv\Scripts\python.exe"
if not exist "%PY_EXE%" (
    set "PY_EXE=python"
)

echo [1/2] 正在启动后台调度引擎与 Web 服务 (端口: 8088)...
start "" http://127.0.0.1:8088

echo [2/2] 服务已启动，正在监听 http://127.0.0.1:8088
echo 提示：按 Ctrl+C 可停止服务。
echo.

"%PY_EXE%" -m video_farm.web --port 8088

pause
