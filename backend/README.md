# 后端启动与验证

## 1. 技术与目录

Python 3.12+、Django 5.2、Django REST Framework、Simple JWT、drf-spectacular、Celery、MySQL、Redis、MQTT。

```text
backend/
  config/                     Django、Celery、路由配置
  library/models.py           数据实体与约束
  library/api/                权限、输入验证、REST 接口与 OpenAPI 注解
  library/services/           认证、流通、支付、设备与运营业务事务
  library/adapters.py          MQTT 接入适配器
  library/tasks.py             预约过期、逾期计费、提醒、离线监测、保留期限清理
  library/management/commands/ 演示初始化、维护任务、MQTT 消费和模拟发布
  library/migrations/          数据库迁移
  library/tests/               接口业务测试
  docs/API.md                 接口索引、调用示例、FR 需求对应与实施边界
```

单体内以 API → 业务服务 → ORM 分层；关键状态变更通过服务执行。Django Admin 对流通等领域记录只读，避免绕过借还状态机。用户管理后台保留超级管理员维护能力，并记录修改审计。

## 2. Windows 本地运行

以下命令在仓库根目录执行。如果系统 `python` 指向 Microsoft Store 占位程序，请使用实际 Python 可执行文件路径执行第一条命令。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
.\.venv\Scripts\python.exe backend/manage.py migrate
.\.venv\Scripts\python.exe backend/manage.py seed_demo --password 'Library-Demo-2026!'
.\.venv\Scripts\python.exe backend/manage.py runserver 127.0.0.1:8000
```

演示账号如下，密码为初始化命令的 `--password`。重复初始化不会覆盖已有账号密码。

| 手机号 | 角色 |
| --- | --- |
| 13800000001 | 管理员，同时可登录 Django Admin |
| 13800000002 | 读者 |
| 13800000003 | 运维 |

访问 `http://127.0.0.1:8000/api/docs/`，先调用 `/api/v1/auth/login/`，将返回的 `data.access` 填入 Swagger 的 Authorize。接口鉴权头为 `Authorization: Bearer <access>`。JSON 采用 `{code, message, data, request_id}` 统一包装，成功 code=0。Django Admin 初次演示初始化的用户名为 `demo_admin`。

Linux/macOS 使用 `.venv/bin/python` 替换 `.venv\Scripts\python.exe`。本地默认 SQLite，适合演示与测试；MySQL 才提供本项目设计依赖的行锁语义，本地 SQLite 测试不能证明生产并发安全或性能指标。

## 3. Docker / MySQL / Redis / EMQX

复制根目录 `.env.example` 为 `.env`，设置数据库密码与两个不同的随机签名密钥，再执行：

```powershell
Copy-Item .env.example .env
# 编辑 .env 后执行
docker compose up -d mysql redis emqx
docker compose build
docker compose run --rm api python manage.py migrate
docker compose run --rm api python manage.py collectstatic --noinput
docker compose run --rm api python manage.py seed_demo --password 'Library-Demo-2026!'
docker compose up -d api worker beat mqtt nginx backup
```

先迁移数据库再启动任务进程。Nginx 入口为 `http://127.0.0.1:8080`，API 也映射到 `127.0.0.1:8000`，EMQX MQTT 映射到 `127.0.0.1:1883`；MySQL 和 Redis 不映射宿主机端口。此 Compose 为开发/演示组合，MQTT broker 未配置生产认证和 ACL。

backup 服务启动后及每隔 24 小时执行一次事务一致的 MySQL 逻辑备份，保存至根目录 backups/（已被 Git 忽略），不自动删除历史备份。恢复应在独立测试库先验证；字段解密密钥须与备份分别妥善保存，否则无法恢复敏感字段。

生产部署需设置 `DJANGO_DEBUG=0`、`SIMULATION_ENABLED=0`，配置真实 `ALLOWED_HOSTS`、HTTPS 网关、MQTT 身份与 topic ACL、数据库备份及外部供应商适配。真实支付/短信/实名认证供应商、设备实际命令执行、主备切换和性能压测不由此演示配置提供。关闭模拟后相关模拟操作明确拒绝，不会伪装完成真实操作。

环境变量：

| 变量 | 作用 |
| --- | --- |
| DJANGO_DEBUG | 默认 `1`；生产设置 `0` |
| DJANGO_SECRET_KEY | Django/JWT 密钥；生产不能使用代码内开发默认值 |
| MYSQL_HOST / MYSQL_PORT / MYSQL_DATABASE / MYSQL_USER / MYSQL_PASSWORD | 设置 MYSQL_HOST 后启用 MySQL；否则 SQLite |
| REDIS_URL | 缓存、节流、验证码共享及 Celery broker；未设置时本地缓存仅单进程 |
| SIMULATION_ENABLED | 开发默认 `1`，生产默认 `0`；控制模拟短信、实名认证、支付、人脸、设备命令 |
| PAYMENT_SIGNING_KEY | 支付回调 HMAC 密钥；回调有效窗口 5 分钟 |
| FIELD_ENCRYPTION_KEY | AES-SIV 字段加密密钥；首次迁移前设置并备份，已有数据后不能直接换值，需数据重加密迁移 |
| DEVICE_SIGNING_KEY | 设备命令 HMAC 签名密钥，真实设备需配置对应验签与防重放逻辑 |
| CORS_ALLOWED_ORIGINS | 逗号分隔的前端来源，默认 `http://localhost:5173` |
| MQTT_HOST / MQTT_PORT / MQTT_USERNAME / MQTT_PASSWORD / MQTT_TLS | MQTT 连接与 TLS 参数 |

`.env` 由 Docker Compose 加载；本地直接运行时使用 PowerShell `$env:变量名='值'` 设置环境变量，不会自动加载 `.env`。

本地也可在 `backend/config/local_settings.py` 中定义 `LOCAL_ENV` 字典，填写上述环境变量的字符串值。Django 启动时自动加载，终端中已设置的环境变量优先。此文件已被 Git 忽略，用于保存本机数据库连接信息，不会随代码同步。

## 4. 定时任务与设备模拟

不运行 Celery 时，可手动执行一次维护：

```powershell
.\.venv\Scripts\python.exe backend/manage.py run_maintenance
```

Celery Beat 每分钟检查预约过期、逾期计费、即将到期提醒及设备离线，每日清理保留期限已到的数据。一天内重复扫描不会重复累计同一天的罚款、信用扣减或同类提醒。运行 `worker` 和 `beat` 才会自动调度；Windows 本机建议通过 Docker 运行 Celery。

MQTT 收件先持久化再确认，业务处理失败由 Beat 每 5 秒调度重试，每批最多 100 条；`run_maintenance` 也会重试待处理收件。收件持久化失败时订阅端保持消息未确认并重连，依靠 broker 的持久会话重发。请使用 QoS 1，保持桥接客户端 ID 唯一且稳定。此机制不能保证 QoS 0 的断线重发。

MQTT 事件主题为 `library/{siteId}/device/{deviceId}/event`，同时支持同前缀的 telemetry 和 status：

```json
{
  "event_id": "76434b4b-a171-4a33-b246-82a7b805d2c7",
  "kind": "smoke",
  "payload": {"message": "模拟烟感告警"}
}
```

```powershell
docker compose exec api python manage.py simulate_device --device 1 --kind heartbeat
```

设备须先登记。事件类型包含 `heartbeat / telemetry / fault / smoke / help / security / rfid_exit / inventory`。事件 UUID 去重；同一 UUID 修改内容会拒绝。`rfid_exit` 使用 `payload.rfids`；`inventory` 使用 `payload.shelf` 和 `payload.observed`。设备端可按周期推送盘点事件，服务端保存盘亏、盘盈和错架报告。模拟烟感会生成告警、工单和门禁解锁命令记录，状态为 `simulated`，并不操作真实硬件。也可直接使用 REST 设备事件接口完成同样的演示。

## 5. 验证

```powershell
.\.venv\Scripts\python.exe backend/manage.py check
.\.venv\Scripts\python.exe backend/manage.py test library.tests
.\.venv\Scripts\python.exe backend/manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe backend/manage.py spectacular --file backend/openapi.yaml --validate --fail-on-warn
```

测试覆盖业务规则、权限隔离、幂等、预约队列、计费、支付签名、状态流转、设备事件、扫码认证、隐私清理及 OpenAPI 鉴权。测试数据库独立创建和销毁，不使用演示数据。

当前验证环境为 Windows / Python 3.14 / SQLite。Docker 服务、真实 MySQL 并发、MQTT broker 实连和需求中的 500 并发/99.9% 可用性需要在相应部署环境另行验收，不能从 SQLite 单元测试推断已达标。

自动化测试包含原有业务流程，以及资料/工单并发交错、离线跨账号去重、MQTT 持久化确认和失败重试、节假日本地时区等回归场景。此前实际 HTTP 已完成手机号登录 → 检索副本 → 借书 → 跨角色消毒/上架的归还闭环。

升级时先暂停 API、worker、beat 和 MQTT 桥接进程，再执行 `manage.py migrate`。迁移 0008/0009 新增收件箱和离线交易回执，并将旧的离线幂等结果迁入全局回执；若同一个历史事件 ID 已产生不同交易结果，迁移会报告冲突并停止，需先核对历史记录，不能直接忽略冲突。升级完成后重启服务，避免新旧进程同时写入两套离线去重表。

`/health/` 为存活探针，`/health/ready/` 检查数据库与缓存。设备在线状态由心跳/超时监测提供，不通过公开健康检查泄露设备详情。

## 6. 实现依据

项目内需求文档与架构设计决定业务范围。事务边界和 API 权限设计参考 [Django 事务文档](https://docs.djangoproject.com/en/5.2/topics/db/transactions/) 与 [DRF 权限文档](https://www.django-rest-framework.org/api-guide/permissions/)。

字段加密使用 [Cryptography 的 AES-SIV 实现](https://cryptography.io/en/49.0.0/hazmat/primitives/aead/)，确定性加密仅用于需精确匹配的字段，会暴露相等关系，不支持密文模糊检索。密钥独立于数据库保存。
# 分工与核心接口入口

王恒负责的核心 API、服务文件及新增联调路径见 [接口分工说明](../docs/api/README.md)。可直接导入 [Postman 集合](../docs/api/postman_collection.json)，原 `/api/v1/` 接口继续可用。
