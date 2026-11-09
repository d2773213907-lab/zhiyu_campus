@echo off
chcp 65001 >nul
title 知屿校园 - 公网隧道（手机可访问）

if not exist "%~dp0_tools\隧道.ps1" (
    echo [错误] 找不到 _tools\隧道.ps1
    pause
    exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0_tools\隧道.ps1"

pause
