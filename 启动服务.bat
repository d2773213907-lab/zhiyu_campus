@echo off
chcp 65001 >nul
title 知屿校园 - 启动器

cd /d "%~dp0backend"

where python >nul 2>nul
if errorlevel 1 (
    echo.
    echo [错误] 没有找到 python 命令。
    echo 请先安装 Python 3.10 或更高版本：
    echo     https://www.python.org/downloads/
    echo 安装时务必勾选 "Add Python to PATH"。
    echo.
    pause
    exit /b 1
)

python launcher.py

echo.
echo 服务已停止，按任意键关闭窗口。
pause >nul
