# 成员 C 答辩环境一键准备（Windows PowerShell）
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

Write-Host "=== 1. 检查 Docker EMQX ===" -ForegroundColor Cyan
$emqx = docker ps --filter "name=emqx" --format "{{.Names}}" 2>$null
if (-not $emqx) {
    Write-Host "启动 emqx..." 
    docker compose up -d emqx
    Start-Sleep -Seconds 5
}

Write-Host "=== 2. 初始化后端数据 ===" -ForegroundColor Cyan
$py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    python -m venv .venv
    & $py -m pip install -r backend/requirements.txt -q
    & $py -m pip install -r iot-simulator/requirements.txt -q
}
& $py backend/manage.py migrate
& $py backend/manage.py seed_demo --password "Library-Demo-2026!"
& $py iot-simulator/seed_devices.py

Write-Host "=== 3. MQTT 自检 ===" -ForegroundColor Cyan
& $py iot-simulator/verify_mqtt.py
if ($LASTEXITCODE -ne 0) {
    Write-Host "MQTT 未就绪，请先: docker compose up -d emqx api mqtt" -ForegroundColor Yellow
    exit 1
}

Write-Host "=== 4. 发送答辩演示事件 ===" -ForegroundColor Cyan
& $py iot-simulator/run_demo.py

Write-Host "`n完成。接下来可：" -ForegroundColor Green
Write-Host "  - 打开 http://127.0.0.1:8000/api/docs/ 查看 device-events / alerts"
Write-Host "  - 运行 python iot-simulator/simulator.py 进入交互菜单"
