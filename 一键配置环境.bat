@echo off
chcp 65001 >nul
title Video Farm 视频工坊 · 跨机环境一键初始化
cls

echo ============================================================
echo   🎬 Video Farm 视频工坊 · 跨机环境一键初始化与依赖安装
echo ============================================================
echo.

cd /d "%~dp0"

:: 1. 检查 Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未检测到系统 Python，请先安装 Python 3.10 或更高版本，并勾选 Add to PATH！
    echo 下载地址: https://www.python.org/downloads/
    pause
    exit /b 1
)
echo [1/5] 检测到系统 Python:
python --version

:: 2. 检查或创建独立虚拟环境 .venv
if not exist ".venv" (
    echo [2/5] 正在创建本地独立虚拟环境 (.venv)...
    python -m venv .venv
    if %errorlevel% neq 0 (
        echo [警告] 创建虚拟环境失败，尝试使用当前 Python...
    ) else (
        echo [2/5] 独立虚拟环境 .venv 创建成功！
    )
) else (
    echo [2/5] 检测到已有虚拟环境 .venv，跳过创建。
)

set "PY_BIN=.venv\Scripts\python.exe"
set "PIP_BIN=.venv\Scripts\pip.exe"
if not exist "%PY_BIN%" (
    set "PY_BIN=python"
    set "PIP_BIN=pip"
)

:: 3. 安装核心依赖
echo.
echo [3/5] 正在安装 Video Farm 核心依赖库 (FastAPI, OpenCV, Playwright, Edge-TTS 等)...
"%PIP_BIN%" install --upgrade pip
"%PIP_BIN%" install -r requirements.txt
if %errorlevel% neq 0 (
    echo [警告] 部分依赖安装可能有警告，请检查上方日志。
)

:: 4. 初始化 Playwright 真实浏览器内核
echo.
echo [4/5] 正在初始化 Playwright 浏览器内核 (Chromium)...
"%PY_BIN%" -m playwright install chromium

:: 5. 检查 gflow-cli 首尾帧引擎
echo.
echo [5/5] 检查 Google Flow 首尾帧引擎 (gflow-cli)...
if not exist "gflow-cli" (
    echo 正在从 GitHub 克隆 gflow-cli 引擎仓库...
    git clone https://github.com/ffroliva/gflow-cli.git gflow-cli
    if exist "gflow-cli" (
        cd gflow-cli
        git checkout b747ea56 2>nul
        cd ..
        echo gflow-cli 克隆并切换到首尾帧增强版本成功！
    ) else (
        echo [提示] 未能自动克隆 gflow-cli，可手动将 gflow-cli 复制到本目录下。
    )
) else (
    echo gflow-cli 目录已存在，就绪。
)

:: 6. 检查 FFmpeg
echo.
ffmpeg -version >nul 2>&1
if %errorlevel% neq 0 (
    echo [提示] 系统环境变量中未找到 ffmpeg 命令。
    echo 如果需要音视频拼接与母片合成，请确保安装了 ffmpeg 并加入 PATH！
) else (
    echo [OK] FFmpeg 检测正常！
)

echo.
echo ============================================================
echo   🎉 环境配置完成！你可以直接双击运行【启动视频工坊.bat】！
echo ============================================================
echo.
pause
