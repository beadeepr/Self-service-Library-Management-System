#!/usr/bin/env bash
# 无人值守图书馆系统 —— 一键启动（Git Bash / WSL / Linux / macOS）
#
#   ./start.sh                 Docker 启动（默认，答辩推荐），入口 http://127.0.0.1:8081
#   ./start.sh --local         本机双进程：Django :8000 + Vite :5173
#   ./start.sh --rebuild       强制重建镜像
#   ./start.sh --skip-seed     跳过演示数据初始化
#   ./start.sh --no-browser    不自动打开浏览器
#
# 与 start.ps1 行为一致，二者只需其一。

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

MODE=docker
REBUILD=0
SKIP_SEED=0
NO_BROWSER=0

ADMIN_PASSWORD='Library-Demo-2026!'
READER_PASSWORD='Reader-Demo-2026!'
DOCKER_FRONT='http://127.0.0.1:8081'
LOCAL_FRONT='http://127.0.0.1:5173'

usage() {
    sed -n '2,10p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

for arg in "$@"; do
    case "$arg" in
        --local|local)        MODE=local ;;
        --docker|docker)      MODE=docker ;;
        --rebuild|-r)         REBUILD=1 ;;
        --skip-seed)          SKIP_SEED=1 ;;
        --no-browser)         NO_BROWSER=1 ;;
        -h|--help)            usage; exit 0 ;;
        *) echo "未知参数：$arg" >&2; usage; exit 1 ;;
    esac
done

if [ -t 1 ]; then
    C_CYAN=$'\033[36m'; C_GREEN=$'\033[32m'; C_YELLOW=$'\033[33m'; C_RED=$'\033[31m'; C_DIM=$'\033[2m'; C_OFF=$'\033[0m'
else
    C_CYAN=''; C_GREEN=''; C_YELLOW=''; C_RED=''; C_DIM=''; C_OFF=''
fi

step() { printf '\n%s== %s%s\n' "$C_CYAN" "$1" "$C_OFF"; }
ok()   { printf '   %s[OK]%s %s\n' "$C_GREEN" "$C_OFF" "$1"; }
warn() { printf '   %s[!]%s %s\n' "$C_YELLOW" "$C_OFF" "$1"; }
die()  { printf '\n%s[启动失败]%s %s\n' "$C_RED" "$C_OFF" "$1" >&2; exit 1; }

random_hex() {
    if command -v openssl >/dev/null 2>&1; then
        openssl rand -hex "$1"
    else
        od -An -tx1 -N "$1" /dev/urandom | tr -d ' \n'
    fi
}

new_env_file() {
    [ -f .env.example ] || die '缺少 .env.example，无法生成 .env'
    local tmp; tmp="$(mktemp)"
    : > "$tmp"
    while IFS= read -r line || [ -n "$line" ]; do
        case "$line" in
            DJANGO_SECRET_KEY=*)    printf 'DJANGO_SECRET_KEY=%s\n' "$(random_hex 32)" >> "$tmp" ;;
            MYSQL_PASSWORD=*)       printf 'MYSQL_PASSWORD=lib%s\n' "$(random_hex 12)" >> "$tmp" ;;
            MYSQL_ROOT_PASSWORD=*)  printf 'MYSQL_ROOT_PASSWORD=root%s\n' "$(random_hex 12)" >> "$tmp" ;;
            PAYMENT_SIGNING_KEY=*)  printf 'PAYMENT_SIGNING_KEY=%s\n' "$(random_hex 32)" >> "$tmp" ;;
            FIELD_ENCRYPTION_KEY=*) printf 'FIELD_ENCRYPTION_KEY=%s\n' "$(random_hex 32)" >> "$tmp" ;;
            DEVICE_SIGNING_KEY=*)   printf 'DEVICE_SIGNING_KEY=%s\n' "$(random_hex 32)" >> "$tmp" ;;
            *)                      printf '%s\n' "$line" >> "$tmp" ;;
        esac
    done < .env.example
    mv "$tmp" .env
}

port_in_use() {
    local port=$1
    if command -v ss >/dev/null 2>&1; then
        ss -ltn "sport = :$port" 2>/dev/null | grep -q LISTEN
    elif command -v lsof >/dev/null 2>&1; then
        lsof -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1
    else
        netstat -an 2>/dev/null | grep -E "[:.]$port[[:space:]].*LISTEN" >/dev/null 2>&1
    fi
}

assert_port() {
    local port=$1 name=$2
    if port_in_use "$port"; then
        die "端口 $port（$name）已被占用。请先结束该进程再启动。"
    fi
}

# Docker 已在运行本项目时，端口应归本项目所有，不做拦截
assert_port_docker() {
    local port=$1 name=$2
    if [ -n "$(docker compose ps -q 2>/dev/null)" ]; then
        return 0
    fi
    assert_port "$port" "$name"
}

wait_healthy() {
    local service=$1 timeout=${2:-120} start=$SECONDS cid status
    while [ $((SECONDS - start)) -lt "$timeout" ]; do
        cid="$(docker compose ps -q "$service" 2>/dev/null | head -n 1 || true)"
        if [ -n "$cid" ]; then
            status="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$cid" 2>/dev/null || echo unknown)"
            case "$status" in
                healthy)          return 0 ;;
                unhealthy|exited) return 1 ;;
            esac
        fi
        sleep 2
    done
    return 1
}

wait_http() {
    local url=$1 timeout=${2:-90} start=$SECONDS
    while [ $((SECONDS - start)) -lt "$timeout" ]; do
        if curl -fsS -o /dev/null --max-time 3 "$url" 2>/dev/null; then
            return 0
        fi
        sleep 2
    done
    return 1
}

open_browser() {
    local url=$1
    if command -v cmd.exe >/dev/null 2>&1; then
        cmd.exe /c start "" "$url" >/dev/null 2>&1 || true
    elif command -v xdg-open >/dev/null 2>&1; then
        xdg-open "$url" >/dev/null 2>&1 || true
    elif command -v open >/dev/null 2>&1; then
        open "$url" >/dev/null 2>&1 || true
    fi
}

show_summary() {
    local front=$1 admin_url=$2 docs=$3 stop_hint=$4
    printf '\n%s====================================================%s\n' "$C_GREEN" "$C_OFF"
    printf '%s  演示环境已就绪%s\n' "$C_GREEN" "$C_OFF"
    printf '%s====================================================%s\n' "$C_GREEN" "$C_OFF"
    printf '  三端界面（读者 / 自助终端 / 管理后台）: %s\n' "$front"
    printf '  API / Django Admin                   : %s\n' "$admin_url"
    printf '  Swagger 接口文档                     : %s\n' "$docs"
    printf '\n  演示账号\n'
    printf '    13800000001  管理员     / Library-Demo-2026!\n'
    printf '    13800000002  读者       / Library-Demo-2026!  <- 主演示账号\n'
    printf '    13800000003  运维       / Library-Demo-2026!\n'
    printf '    13480588246  读者(逾期) / Reader-Demo-2026!\n'
    printf '    13380588246  读者(持书) / Reader-Demo-2026!\n'
    printf '\n%s  停止：%s%s\n\n' "$C_DIM" "$stop_hint" "$C_OFF"
}

start_docker() {
    step '检查 Docker'
    docker info --format '{{.ServerVersion}}' >/dev/null 2>&1 \
        || die '无法连接 Docker。请先启动 Docker Desktop，等其就绪后重试。'
    ok 'Docker 已就绪'

    step '检查环境变量文件 .env'
    if [ -f .env ]; then
        ok '.env 已存在，沿用其中的密钥'
    else
        new_env_file
        ok '.env 已按 .env.example 生成，并填入随机密钥'
        warn 'FIELD_ENCRYPTION_KEY 建库后不可更换，否则已加密字段无法解密；请勿删除 .env'
    fi

    step '检查端口'
    assert_port_docker 8081 '前端'
    assert_port_docker 8080 'API / Django Admin'
    assert_port_docker 8000 'API 直连'
    assert_port_docker 1883 'MQTT'
    ok '8081 / 8080 / 8000 / 1883 可用'

    step '启动依赖服务（MySQL / Redis / EMQX）'
    docker compose up -d mysql redis emqx >/dev/null 2>&1 \
        || die '启动依赖服务失败，请手动执行 docker compose up -d mysql redis emqx 查看原因'
    wait_healthy mysql 180 || die 'MySQL 未在 180 秒内就绪，执行 docker compose logs mysql 查看原因'
    wait_healthy redis 60  || die 'Redis 未就绪，执行 docker compose logs redis 查看原因'
    ok 'MySQL / Redis 健康'

    if [ "$REBUILD" -eq 1 ] || [ -z "$(docker compose ps -a -q api 2>/dev/null | head -n 1 || true)" ]; then
        step '构建镜像（首次约 1~3 分钟，后端依赖有缓存）'
        docker compose build || die '镜像构建失败'
        ok '镜像构建完成'
    else
        ok '镜像已存在，跳过构建（改了代码请加 --rebuild）'
    fi

    step '初始化数据库'
    docker compose run --rm api python manage.py migrate --noinput || die '数据库迁移失败'
    docker compose run --rm api python manage.py collectstatic --noinput >/dev/null || die '静态文件收集失败'
    ok '数据库结构与静态文件已就绪'

    if [ "$SKIP_SEED" -eq 1 ]; then
        ok '已指定 --skip-seed，跳过演示数据'
    else
        step '初始化演示数据（可重复执行，不会重复造数据）'
        docker compose run --rm api python manage.py seed_demo --password "$ADMIN_PASSWORD" || die 'seed_demo 失败'
        docker compose run --rm api python manage.py seed_demo_showcase --password "$READER_PASSWORD" || die 'seed_demo_showcase 失败'
        ok '演示数据已就绪'
    fi

    step '启动全部服务'
    docker compose up -d >/dev/null 2>&1 \
        || die '启动服务失败，请手动执行 docker compose up -d 查看原因'
    wait_healthy frontend 120 || warn '前端容器未报告健康，请执行 docker compose logs frontend 检查'
    wait_http 'http://127.0.0.1:8000/health/' 90 || die 'API 未响应 http://127.0.0.1:8000/health/ ，执行 docker compose logs api 查看原因'
    ok '前端与 API 均已响应'

    show_summary "$DOCKER_FRONT" 'http://127.0.0.1:8080' 'http://127.0.0.1:8000/api/docs/' \
        'docker compose down（保留数据）；docker compose down -v（清空数据库）'
    [ "$NO_BROWSER" -eq 1 ] || open_browser "$DOCKER_FRONT"
}

find_python() {
    local candidate
    for candidate in .venv/Scripts/python.exe venv/Scripts/python.exe .venv/bin/python venv/bin/python; do
        if [ -x "$candidate" ]; then
            printf '%s\n' "$candidate"
            return 0
        fi
    done
    if command -v python3 >/dev/null 2>&1; then command -v python3; return 0; fi
    if command -v python >/dev/null 2>&1; then command -v python; return 0; fi
    die '未找到 Python。请安装 Python 3.12 后重试（或先手动创建 .venv）。'
}

start_local() {
    # Git Bash / WSL 的终端是 UTF-8；不指定时 Python 会按系统代码页（GBK）输出，中文会乱码
    export PYTHONIOENCODING=utf-8

    step '检查 Python 环境'
    local python; python="$(find_python)"
    if ! "$python" -c 'import django, rest_framework, celery' >/dev/null 2>&1; then
        step '安装后端依赖'
        "$python" -m pip install --disable-pip-version-check -r backend/requirements.txt || die '后端依赖安装失败'
    fi
    ok "使用 $python"

    command -v npm >/dev/null 2>&1 || die '未找到 npm。请安装 Node >= 20（本项目在 Node 24 上验证）。'
    if [ ! -d frontend/node_modules ]; then
        step '安装前端依赖（首次约 1 分钟）'
        ( cd frontend && npm install ) || die 'npm install 失败'
    fi
    ok '前端依赖已就绪'

    step '检查端口'
    assert_port 8000 'Django'
    assert_port 5173 'Vite'
    ok '8000 / 5173 可用'

    step '初始化数据库（SQLite：backend/db.sqlite3）'
    "$python" backend/manage.py migrate --noinput || die '数据库迁移失败'
    if [ "$SKIP_SEED" -eq 1 ]; then
        ok '已指定 --skip-seed，跳过演示数据'
    else
        "$python" backend/manage.py seed_demo --password "$ADMIN_PASSWORD" || die 'seed_demo 失败'
        "$python" backend/manage.py seed_demo_showcase --password "$READER_PASSWORD" || die 'seed_demo_showcase 失败'
        ok '演示数据已就绪'
    fi

    step '启动后端（前台日志留在本窗口）'
    "$python" backend/manage.py runserver 127.0.0.1:8000 &
    BACKEND_PID=$!
    trap 'kill "$BACKEND_PID" 2>/dev/null || true' EXIT INT TERM

    wait_http 'http://127.0.0.1:8000/health/' 90 || die 'Django 未在 90 秒内响应，请查看上方日志'
    ok '后端已响应'

    show_summary "$LOCAL_FRONT" 'http://127.0.0.1:8000/admin/' 'http://127.0.0.1:8000/api/docs/' \
        '在本窗口按 Ctrl+C（会一并停止后端）'
    [ "$NO_BROWSER" -eq 1 ] || open_browser "$LOCAL_FRONT"

    step '启动前端（Ctrl+C 停止）'
    cd frontend
    npm run dev
}

printf '无人值守图书馆系统 · 启动脚本\n模式：%s\n' "$MODE"

if [ "$MODE" = docker ]; then
    start_docker
else
    start_local
fi
