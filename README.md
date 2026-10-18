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
- 运行后交互文档：`http://127.0.0.1:8000/api/docs/`

需求文档、架构设计、架构评审与三人分工见仓库根目录的同名 Markdown 文件。

## 快速开始

### 本地开发（两个进程）

```powershell
# 1. 后端：127.0.0.1:8000
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
.\.venv\Scripts\python.exe backend/manage.py migrate
.\.venv\Scripts\python.exe backend/manage.py seed_demo --password 'Library-Demo-2026!'
.\.venv\Scripts\python.exe backend/manage.py runserver 127.0.0.1:8000

# 2. 前端：另开一个终端，打开 http://127.0.0.1:5173
cd frontend
npm install
npm run dev
```

演示账号：`13800000001`（管理员）/ `13800000002`（读者）/ `13800000003`（运维），
口令为 `seed_demo` 的 `--password`。三端入口与更完整的演示数据见
[`frontend/README.md`](frontend/README.md)。

### Docker

一条命令式启动（含前端、MySQL、Redis、Celery、EMQX），步骤见
[`frontend/README.md`](frontend/README.md) 的「Docker 部署」一节。

## 运行说明

本地可使用 SQLite 演示；Docker 配置提供 MySQL、Redis、Celery 和 EMQX。
支付、短信、身份核验及设备控制默认使用显式模拟流程，不会伪装成真实供应商已完成对接。
