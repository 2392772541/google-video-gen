@echo off
chcp 65001 >nul
title 注册 Codex 本地技能 · 谷歌视频生成
cls

echo ============================================================
echo   🤖 注册 Codex 本地技能：谷歌视频生成 (google-video-gen)
echo ============================================================
echo.

cd /d "%~dp0"

set "TARGET_DIR=%USERPROFILE%\.codex\skills\google-video-gen"

echo 正在复制技能定义文件到: %TARGET_DIR%
if not exist "%TARGET_DIR%" mkdir "%TARGET_DIR%"

xcopy /E /Y /I "skills\google-video-gen" "%TARGET_DIR%" >nul

if %errorlevel% equ 0 (
    echo.
    echo ============================================================
    echo   🎉 注册成功！
    echo   现在你在任何 Codex 窗口中输入：
    echo   “帮我调用谷歌视频生成” 或 “$google-video-gen”
    echo   即可随时唤醒本项目进行视频生产和调度！
    echo ============================================================
) else (
    echo.
    echo [错误] 技能文件复制失败，请检查写入权限。
)
echo.
pause
