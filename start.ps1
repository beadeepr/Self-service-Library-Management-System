#Requires -Version 5.1
<#
.SYNOPSIS
    无人值守图书馆系统 —— 一键启动

.DESCRIPTION
    docker（默认）：MySQL / Redis / EMQX / Celery / 前端全部由 compose 托管，
                    入口 http://127.0.0.1:8081 ，答辩建议用这一种。
    local        ：本机 SQLite + Django runserver(:8000) + Vite(:5173)，
                    需要本机已安装 Python 3.12 与 Node >= 20。

.EXAMPLE
    .\start.ps1                    # Docker 启动，缺什么补什么，可重复执行
    .\start.ps1 -Mode local        # 本机双进程启动
    .\start.ps1 -Rebuild           # 强制重建镜像（改了后端/前端代码后用）
    .\start.ps1 -SkipSeed          # 不重新初始化演示数据
    .\start.ps1 -NoBrowser         # 启动后不自动打开浏览器
#>
[CmdletBinding()]
param(
    [ValidateSet('docker', 'local')]
    [string]$Mode = 'docker',
    [switch]$Rebuild,
    [switch]$SkipSeed,
    [switch]$NoBrowser
)

# PS 5.1 在 Stop 模式下会把原生命令（docker / python / npm）写到 stderr 的进度信息
# 当成终止性异常（NativeCommandError）。本脚本统一以退出码判断成败，因此降到 Continue。
$ErrorActionPreference = 'Continue'
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch { }
Set-Location -LiteralPath $PSScriptRoot

# 与 backend/README.md、frontend/README.md、seed_demo 的约定保持一致
$ADMIN_PASSWORD = 'Library-Demo-2026!'
$READER_PASSWORD = 'Reader-Demo-2026!'
$DOCKER_FRONT = 'http://127.0.0.1:8081'
$LOCAL_FRONT = 'http://127.0.0.1:5173'

function Write-Step([string]$Text) { Write-Host "`n== $Text" -ForegroundColor Cyan }
function Write-Ok([string]$Text) { Write-Host "   [OK] $Text" -ForegroundColor Green }
function Write-Warn([string]$Text) { Write-Host "   [!] $Text" -ForegroundColor Yellow }
function Fail([string]$Text) {
    Write-Host "`n[启动失败] $Text" -ForegroundColor Red
    exit 1
}

# ---------------------------------------------------------------- 通用工具

function New-RandomHex([int]$Bytes) {
    $buffer = New-Object byte[] $Bytes
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($buffer)
    return (($buffer | ForEach-Object { $_.ToString('x2') }) -join '')
}

function Assert-PortAvailable([int]$Port, [string]$Name) {
    $connections = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if (-not $connections) { return }
    $names = @()
    foreach ($ownerPid in ($connections | Select-Object -ExpandProperty OwningProcess -Unique)) {
        $process = Get-Process -Id $ownerPid -ErrorAction SilentlyContinue
        if ($process -and $process.ProcessName -like 'com.docker.backend*') {
            # Docker Desktop 的端口代理，说明是本项目已经在跑，无需拦截
            return
        }
        $names += $(if ($process) { "$($process.ProcessName) (PID $ownerPid)" } else { "PID $ownerPid" })
    }
    Fail "端口 $Port（$Name）已被占用：$($names -join '，')。请先结束该进程再启动。"
}

function Wait-Healthy([string]$Service, [int]$TimeoutSeconds = 120) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $container = (& docker compose ps -q $Service 2>$null | Select-Object -First 1)
        if ($container) {
            $status = & docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' $container 2>$null
            if ($status -eq 'healthy') { return $true }
            if ($status -eq 'unhealthy' -or $status -eq 'exited') { return $false }
        }
        Start-Sleep -Seconds 2
    }
    return $false
}

function Wait-Http([string]$Url, [int]$TimeoutSeconds = 90) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) { return $true }
        } catch {
            # 服务尚未就绪，继续等待
        }
        Start-Sleep -Seconds 2
    }
    return $false
}

function New-EnvFile {
    $values = @{
        DJANGO_SECRET_KEY    = New-RandomHex 32
        MYSQL_PASSWORD       = 'lib' + (New-RandomHex 12)
        MYSQL_ROOT_PASSWORD  = 'root' + (New-RandomHex 12)
        PAYMENT_SIGNING_KEY  = New-RandomHex 32
        FIELD_ENCRYPTION_KEY = New-RandomHex 32
        DEVICE_SIGNING_KEY   = New-RandomHex 32
    }
    $lines = Get-Content -LiteralPath '.env.example' -Encoding UTF8
    $output = foreach ($line in $lines) {
        if ($line -match '^([A-Z_]+)=(.*)$' -and $values.ContainsKey($matches[1])) {
            "$($matches[1])=$($values[$matches[1]])"
        } else {
            $line
        }
    }
    $path = Join-Path -Path $PSScriptRoot -ChildPath '.env'
    [IO.File]::WriteAllText($path, ($output -join "`r`n") + "`r`n", (New-Object System.Text.UTF8Encoding($false)))
}

function Show-Summary([string]$Frontend, [string]$AdminUrl, [string]$DocsUrl, [string]$StopHint) {
    Write-Host ''
    Write-Host '====================================================' -ForegroundColor Green
    Write-Host '  演示环境已就绪' -ForegroundColor Green
    Write-Host '====================================================' -ForegroundColor Green
    Write-Host "  三端界面（读者 / 自助终端 / 管理后台）: $Frontend"
    Write-Host "  API / Django Admin                   : $AdminUrl"
    Write-Host "  Swagger 接口文档                     : $DocsUrl"
    Write-Host ''
    Write-Host '  演示账号' -ForegroundColor Cyan
    Write-Host '    13800000001  管理员    / Library-Demo-2026!'
    Write-Host '    13800000002  读者      / Library-Demo-2026!  ← 主演示账号'
    Write-Host '    13800000003  运维      / Library-Demo-2026!'
    Write-Host '    13480588246  读者(逾期) / Reader-Demo-2026!'
    Write-Host '    13380588246  读者(持书) / Reader-Demo-2026!'
    Write-Host ''
    Write-Host '  IoT 答辩演示（另开终端）' -ForegroundColor Cyan
    Write-Host '    pip install -r iot-simulator/requirements.txt'
    Write-Host '    python iot-simulator/seed_devices.py'
    Write-Host '    python iot-simulator/run_demo.py'
    Write-Host ''
    Write-Host "  停止：$StopHint" -ForegroundColor DarkGray
    Write-Host ''
}

# ---------------------------------------------------------------- Docker 模式

function Invoke-ComposeStep([string]$Description, [string[]]$Arguments, [switch]$Quiet) {
    if ($Quiet) {
        & docker compose @Arguments *> $null
    } else {
        & docker compose @Arguments
    }
    if ($LASTEXITCODE -ne 0) {
        $command = $Arguments -join ' '
        Fail "$Description（docker compose $command 退出码 $LASTEXITCODE）。请手动执行该命令查看详细输出。"
    }
}

function Start-DockerMode {
    Write-Step '检查 Docker'
    & docker info --format '{{.ServerVersion}}' 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Fail '无法连接 Docker。请先启动 Docker Desktop，等托盘图标变为运行状态后重试。'
    }
    Write-Ok 'Docker 已就绪'

    Write-Step '检查环境变量文件 .env'
    if (Test-Path -LiteralPath '.env') {
        Write-Ok '.env 已存在，沿用其中的密钥'
    } else {
        if (-not (Test-Path -LiteralPath '.env.example')) { Fail '缺少 .env.example，无法生成 .env' }
        New-EnvFile
        Write-Ok '.env 已按 .env.example 生成，并填入随机密钥'
        Write-Warn 'FIELD_ENCRYPTION_KEY 建库后不可更换，否则已加密的字段无法解密；请勿删除 .env'
    }

    Write-Step '检查端口'
    Assert-PortAvailable 8081 '前端'
    Assert-PortAvailable 8080 'API / Django Admin'
    Assert-PortAvailable 8000 'API 直连'
    Assert-PortAvailable 1883 'MQTT'
    Write-Ok '8081 / 8080 / 8000 / 1883 可用'

    Write-Step '启动依赖服务（MySQL / Redis / EMQX）'
    Invoke-ComposeStep '启动依赖服务失败' @('up', '-d', 'mysql', 'redis', 'emqx') -Quiet
    if (-not (Wait-Healthy 'mysql' 180)) { Fail 'MySQL 未在 180 秒内就绪，执行 docker compose logs mysql 查看原因' }
    if (-not (Wait-Healthy 'redis' 60)) { Fail 'Redis 未就绪，执行 docker compose logs redis 查看原因' }
    Write-Ok 'MySQL / Redis 健康'

    $needBuild = $Rebuild -or -not (& docker compose ps -a -q api 2>$null | Select-Object -First 1)
    if ($needBuild) {
        Write-Step '构建镜像（首次约 1~3 分钟，后端依赖有缓存）'
        Invoke-ComposeStep '镜像构建失败' @('build')
        Write-Ok '镜像构建完成'
    } else {
        Write-Ok '镜像已存在，跳过构建（改了代码请加 -Rebuild）'
    }

    Write-Step '初始化数据库'
    Invoke-ComposeStep '数据库迁移失败' @('run', '--rm', 'api', 'python', 'manage.py', 'migrate', '--noinput')
    Invoke-ComposeStep '静态文件收集失败' @('run', '--rm', 'api', 'python', 'manage.py', 'collectstatic', '--noinput') -Quiet
    Write-Ok '数据库结构与静态文件已就绪'

    if ($SkipSeed) {
        Write-Ok '已指定 -SkipSeed，跳过演示数据'
    } else {
        Write-Step '初始化演示数据（可重复执行，不会重复造数据）'
        Invoke-ComposeStep 'seed_demo 失败' @('run', '--rm', 'api', 'python', 'manage.py', 'seed_demo', '--password', $ADMIN_PASSWORD)
        Invoke-ComposeStep 'seed_demo_showcase 失败' @('run', '--rm', 'api', 'python', 'manage.py', 'seed_demo_showcase', '--password', $READER_PASSWORD)
        Write-Ok '演示数据已就绪'
    }

    Write-Step '启动全部服务'
    Invoke-ComposeStep '启动服务失败' @('up', '-d') -Quiet
    if (-not (Wait-Healthy 'frontend' 120)) {
        Write-Warn '前端容器未报告健康，请执行 docker compose logs frontend 检查'
    }
    if (-not (Wait-Http 'http://127.0.0.1:8000/health/' 90)) {
        Fail 'API 未响应 http://127.0.0.1:8000/health/ ，执行 docker compose logs api 查看原因'
    }
    Write-Ok '前端与 API 均已响应'

    Show-Summary $DOCKER_FRONT 'http://127.0.0.1:8080' 'http://127.0.0.1:8000/api/docs/' 'docker compose down （保留数据）；docker compose down -v （清空数据库）'
    if (-not $NoBrowser) { Start-Process $DOCKER_FRONT }
}

# ---------------------------------------------------------------- 本地模式

function Find-Python {
    foreach ($candidate in @('.venv\Scripts\python.exe', 'venv\Scripts\python.exe')) {
        if (Test-Path -LiteralPath $candidate) { return (Resolve-Path -LiteralPath $candidate).Path }
    }
    $python = Get-Command python -ErrorAction SilentlyContinue
    if (-not $python) { Fail '未找到 Python。请安装 Python 3.12 后重试（或先手动创建 .venv）。' }
    Write-Step '创建虚拟环境 .venv'
    & $python.Source -m venv .venv
    if ($LASTEXITCODE -ne 0) { Fail '创建虚拟环境失败' }
    return (Resolve-Path -LiteralPath '.venv\Scripts\python.exe').Path
}

function Start-LocalMode {
    Write-Step '检查 Python 环境'
    $python = Find-Python
    & $python -c 'import django, rest_framework, celery' 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Step '安装后端依赖'
        & $python -m pip install --disable-pip-version-check -r backend\requirements.txt
        if ($LASTEXITCODE -ne 0) { Fail '后端依赖安装失败' }
    }
    Write-Ok "使用 $python"

    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
        Fail '未找到 npm。请安装 Node >= 20（本项目在 Node 24 上验证）。'
    }
    if (-not (Test-Path -LiteralPath 'frontend\node_modules')) {
        Write-Step '安装前端依赖（首次约 1 分钟）'
        Push-Location frontend
        npm install
        $installCode = $LASTEXITCODE
        Pop-Location
        if ($installCode -ne 0) { Fail 'npm install 失败' }
    }
    Write-Ok '前端依赖已就绪'

    Write-Step '检查端口'
    Assert-PortAvailable 8000 'Django'
    Assert-PortAvailable 5173 'Vite'
    Write-Ok '8000 / 5173 可用'

    Write-Step '初始化数据库（SQLite：backend\db.sqlite3）'
    & $python backend\manage.py migrate --noinput
    if ($LASTEXITCODE -ne 0) { Fail '数据库迁移失败' }
    if (-not $SkipSeed) {
        & $python backend\manage.py seed_demo --password $ADMIN_PASSWORD
        if ($LASTEXITCODE -ne 0) { Fail 'seed_demo 失败' }
        & $python backend\manage.py seed_demo_showcase --password $READER_PASSWORD
        if ($LASTEXITCODE -ne 0) { Fail 'seed_demo_showcase 失败' }
        Write-Ok '演示数据已就绪'
    } else {
        Write-Ok '已指定 -SkipSeed，跳过演示数据'
    }

    Write-Step '启动后端与前端（各自打开一个窗口）'
    $backendCommand = "& '$python' 'backend\manage.py' runserver 127.0.0.1:8000"
    Start-Process -FilePath 'powershell.exe' -ArgumentList "-NoExit -Command `"$backendCommand`"" -WorkingDirectory $PSScriptRoot
    if (-not (Wait-Http 'http://127.0.0.1:8000/health/' 90)) {
        Fail 'Django 未在 90 秒内响应，请查看后端窗口的输出'
    }
    Write-Ok '后端已响应'

    Start-Process -FilePath 'powershell.exe' -ArgumentList "-NoExit -Command `"Set-Location '$PSScriptRoot\frontend'; npm run dev`"" -WorkingDirectory (Join-Path $PSScriptRoot 'frontend')
    if (-not (Wait-Http $LOCAL_FRONT 120)) {
        Write-Warn 'Vite 尚未响应，请查看前端窗口；首次启动可能较慢'
    } else {
        Write-Ok '前端已响应'
    }

    Show-Summary $LOCAL_FRONT 'http://127.0.0.1:8000/admin/' 'http://127.0.0.1:8000/api/docs/' '关闭自动打开的两个窗口（或在窗口中按 Ctrl+C）'
    if (-not $NoBrowser) { Start-Process $LOCAL_FRONT }
}

# ---------------------------------------------------------------- 入口

Write-Host '无人值守图书馆系统 · 启动脚本' -ForegroundColor White
Write-Host "模式：$Mode"

if ($Mode -eq 'docker') { Start-DockerMode } else { Start-LocalMode }
