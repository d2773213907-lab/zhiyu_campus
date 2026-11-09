@echo off
chcp 936 >nul
title 知屿校园 - 开放 8080 端口

net session >nul 2>&1
if errorlevel 1 (
    echo.
    echo   需要管理员权限，正在弹出授权窗口...
    echo   请在弹窗里点【是】。
    echo.
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

echo ============================================================
echo   为「知屿校园」放行 8080 端口
echo ============================================================
echo.

echo [1/3] 删除同名旧规则...
netsh advfirewall firewall delete rule name="知屿校园-8080" >nul 2>&1
echo       完成

echo [2/3] 添加端口规则（8080 / TCP / 所有网络类型）...
netsh advfirewall firewall add rule name="知屿校园-8080" dir=in action=allow protocol=TCP localport=8080 profile=any >nul
if errorlevel 1 (
    echo       [失败] 请确认是管理员窗口
) else (
    echo       成功
)

echo [3/3] 顺带给 python 程序加规则（双保险）...
netsh advfirewall firewall add rule name="知屿校园-python" dir=in action=allow program="%~dp0backend\.venv\Scripts\python.exe" enable=yes profile=any >nul 2>&1
netsh advfirewall firewall add rule name="知屿校园-python-base" dir=in action=allow program="C:\Users\saxtul\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe" enable=yes profile=any >nul 2>&1
echo       完成

echo.
echo ============================================================
echo   当前这台电脑的局域网地址：
echo ============================================================
for /f "tokens=1,2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4"') do (
    for /f "tokens=1" %%c in ("%%b") do (
        echo       http://%%c:8080
    )
)
echo.
echo   手机连同一个 WiFi，直接打开上面的地址即可。
echo   例如：  http://10.30.14.204:8080
echo.
echo   注意：必须先双击「启动服务.bat」把服务跑起来。
echo ============================================================
echo.
pause
