# 无人值守图书馆管理系统

基于需求文档 V2.0 和架构设计的无人值守图书馆系统，包含 Django REST 后端与 Vue 3 三端前端
（读者 Web、自助终端 Kiosk、管理后台）。功能覆盖读者认证、馆藏、借还、预约、罚款、门禁、
设备告警、配送、工单、报表和运营记录。

## 代码与文档入口

- 后端代码：[`backend/`](backend/)
- 后端启动与调用说明：[`backend/README.md`](backend/README.md)
- **前端代码：[`frontend/`](frontend/)**
- **前端启动、三端入口、演示账号与答辩脚本：[`frontend/README.md`](frontend/README.md)**
- 接口清单、业务约定与需求映射：[`backend/docs/API.md`](backend/docs/API.md)
- OpenAPI 文件：[`backend/openapi.yaml`](backend/openapi.yaml)
- **IoT 设备模拟器（答辩演示）：[`iot-simulator/`](iot-simulator/)**
- 运行后交互文档：`http://127.0.0.1:8000/api/docs/`

需求文档、架构设计、架构评审与三人分工见仓库根目录的同名 Markdown 文件。

## 快速开始

### 一键启动（推荐）

仓库根目录提供两个等价的启动脚本：

```powershell
.\start.ps1                  # Docker：初始化并启动全部服务，入口 http://127.0.0.1:8081
.\start.ps1 -Mode local      # 本机双进程：Django :8000 + Vite :5173（SQLite）
```

```bash
./start.sh                   # 同上（Git Bash / WSL / Linux / macOS）
./start.sh --local
```

脚本会检查 Docker（或 Python / Node）、在缺少 `.env` 时按 `.env.example` 生成随机密钥、
按需构建镜像，并依次执行 `migrate`、`collectstatic`、`seed_demo`、`seed_demo_showcase`。
这些步骤都是幂等的，可以反复执行；`-Rebuild`（`--rebuild`）强制重建镜像，
`-SkipSeed`（`--skip-seed`）跳过演示数据，`-NoBrowser`（`--no-browser`）不自动打开浏览器。
需要逐步手工操作时，见 [`frontend/README.md`](frontend/README.md) 的「Docker 部署」一节。

### 本地开发（两个进程）

```powershell
# 1. 后端：127.0.0.1:8000
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
.\.venv\Scripts\python.exe backend/manage.py migrate
.\.venv\Scripts\python.exe backend/manage.py seed_demo --password 'Library-Demo-2026!'
.\.venv\Scripts\python.exe backend/manage.py seed_demo_showcase --password 'Reader-Demo-2026!'
.\.venv\Scripts\python.exe backend/manage.py runserver 127.0.0.1:8000

# 2. 前端：另开一个终端，打开 http://127.0.0.1:5173
cd frontend
npm install
npm run dev
```

演示账号：`13800000001`（管理员）/ `13800000002`（读者）/ `13800000003`（运维），
口令为 `seed_demo` 的 `--password`。三端入口与更完整的演示数据见
[`frontend/README.md`](frontend/README.md)。

### IoT 答辩演示（另开终端）

主系统启动后（`.\start.ps1`），在第二个终端：

```powershell
pip install -r iot-simulator/requirements.txt
python iot-simulator/seed_devices.py
python iot-simulator/run_demo.py          # 自动：心跳 → 烟感 → RFID
python iot-simulator/simulator.py         # 交互菜单
```

详见 [`iot-simulator/README.md`](iot-simulator/README.md)。

## 运行说明

本地可使用 SQLite 演示；Docker 配置提供 MySQL、Redis、Celery 和 EMQX。
支付、短信、身份核验及设备控制默认使用显式模拟流程，不会伪装成真实供应商已完成对接。
