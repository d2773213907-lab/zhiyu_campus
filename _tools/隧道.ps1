# 启动公网隧道：把本机 8080 映射成一个网址，手机/外网都能访问
# 由「启动公网隧道.bat」调用

$ErrorActionPreference = 'Stop'
$log = Join-Path $env:TEMP 'zhiyu-tunnel.out.log'
$errLog = Join-Path $env:TEMP 'zhiyu-tunnel.err.log'
Remove-Item $log, $errLog -Force -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  知屿校园 · 公网隧道" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 1) 检查本地服务
$listen = Get-NetTCPConnection -LocalPort 8080 -State Listen -ErrorAction SilentlyContinue
if (-not $listen) {
    Write-Host "[提示] 8080 上没有服务，请先双击「启动服务.bat」" -ForegroundColor Yellow
    Write-Host "       隧道会启动，但打开网址会显示错误。" -ForegroundColor Yellow
    Write-Host ""
}

# 2) 清掉旧隧道
Get-Process ssh -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1

# 3) 启动新隧道
$sshArgs = @(
    '-o', 'StrictHostKeyChecking=no',
    '-o', 'ServerAliveInterval=20',
    '-o', 'ServerAliveCountMax=3',
    '-o', 'ExitOnForwardFailure=yes',
    '-R', '80:127.0.0.1:8080',
    'serveo.net'
)
$proc = Start-Process -FilePath 'ssh' -ArgumentList $sshArgs -PassThru -WindowStyle Hidden `
    -RedirectStandardOutput $log -RedirectStandardError $errLog

Write-Host "正在连接隧道服务..." -ForegroundColor Gray

# 4) 等待地址出现
$url = $null
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 1
    $text = @()
    if (Test-Path $log) { $text += Get-Content $log -ErrorAction SilentlyContinue }
    if (Test-Path $errLog) { $text += Get-Content $errLog -ErrorAction SilentlyContinue }
    $m = $text | Select-String -Pattern 'https://[a-z0-9\-]+\.serveousercontent\.com' -AllMatches
    if ($m) {
        $url = ($m | ForEach-Object { $_.Matches.Value } | Select-Object -First 1)
        break
    }
    if ($proc.HasExited) { break }
}

if ($url) {
    Write-Host ""
    Write-Host "  手机 / 外网访问地址：" -ForegroundColor Green
    Write-Host ""
    Write-Host "  $url" -ForegroundColor White -BackgroundColor DarkGreen
    Write-Host ""
    Write-Host "  把这个网址发到微信，手机点开就能用，不用装任何东西。" -ForegroundColor Gray
    Write-Host ""
    Write-Host "  注意：这个窗口不能关，电脑不能睡眠，否则网址失效。" -ForegroundColor Yellow
} else {
    Write-Host ""
    Write-Host "[失败] 没能拿到地址。" -ForegroundColor Red
    Write-Host "可能原因：网络不通，或 serveo.net 暂时不可用。" -ForegroundColor Yellow
    if (Test-Path $errLog) {
        Write-Host "--- 错误信息 ---" -ForegroundColor Gray
        Get-Content $errLog | Select-Object -Last 5 | ForEach-Object { Write-Host $_ -ForegroundColor DarkGray }
    }
    Write-Host ""
    Write-Host "按任意键退出..."
    $null = $Host.UI.RawUI.ReadKey('NoEcho,IncludeKeyDown')
    exit 1
}

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  保持此窗口开启。按 Ctrl+C 或关窗口 = 停止隧道" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# 5) 保持窗口，直到隧道结束
try {
    Wait-Process -Id $proc.Id
} catch {
    # 忽略
}
