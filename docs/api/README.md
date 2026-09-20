# 王恒负责的后端接口

本次按《三人分工.md》拆分后端核心代码。设备、告警、门禁、配送、工单、盘点、报表的业务实现仍由刘经纬维护；前端由周硕维护。

## 代码入口

| 模块 | API 文件（backend/library/api/） | 服务文件（backend/library/services/） |
| --- | --- | --- |
| 注册、登录、验证码 | auth.py | auth_service.py |
| 读者、实名、信用、押金、同意记录 | readers.py | reader_service.py |
| 书目、网点、分类、馆藏 | catalog.py | catalog_service.py |
| 借阅、归还、续借 | circulation.py | circulation_service.py |
| 预约 | reservations.py | circulation_service.py |
| 罚款与支付 | fines.py | fine_service.py |
| 规则 | rules.py | rule_engine.py |
| 消息与公告 | notifications.py | circulation_service.py（借还通知） |
| 离线补传 | offline.py | common.py（全局事件去重）、circulation_service.py |

共享视图基类在 `api/base.py`，权限与异常处理在 `api/common.py`，响应包装在 `api/renderers.py`。原 `api/resources.py`、`api/circulation.py`、`api/operations.py` 中已迁出的类保留兼容导入；旧服务模块 `authentication.py`、`circulation.py`、`payments.py` 也保留兼容导入。新功能应修改表中的实现文件。

本次没有修改数据库模型、迁移文件和 MQTT 实现。原 `/api/v1/` 接口继续可用。

## 联调约定

默认地址 `http://127.0.0.1:8000`。JSON 响应为 `{code, message, data, request_id}`；`code=0` 成功，库存不可借为 HTTP 200、`code=4001`，客户端需同时检查业务码。分页数据在 `data.results`。

| 方法与地址 | 请求内容 | 权限 |
| --- | --- | --- |
| POST /api/auth/register/ | phone、password、code、first_name | 匿名；需要注册短信验证码 |
| POST /api/auth/login/ | phone、password | 匿名 |
| POST /api/auth/refresh/ | refresh | 有效刷新令牌 |
| GET /api/books/search/ | q 或 search；可组合 isbn、category、author、active | 公开 |
| POST /api/circulation/borrow/ | copy；管理员可指定 reader | 登录 |
| POST /api/circulation/return/ | loan、branch、damaged（默认 false） | 本人或管理员 |
| POST /api/circulation/renew/ | loan | 本人或管理员 |
| GET /api/circulation/loans/ | 可选 reader、copy、returned_at__isnull 等过滤条件 | 本人记录；管理员可查看全部 |
| GET /api/rules/current/ | 无 | 登录；规则修改仍仅限管理员 |
| POST /api/offline/sync/ | transactions 数组 | 管理员；逐项返回 applied 或 conflict |

借、还、续借必须带 `Idempotency-Key`，同一次操作重试复用键和请求内容；新交易使用新键。还书新入口的 `loan` 对应旧入口 URL 中的 ID，其余请求字段应保持一致；新旧入口共享幂等结果。续借新入口的请求为 `{"loan": 1}`，旧入口为 `/api/v1/loans/1/renew/`。

离线补传每项须包含 UUID `event_id`、`kind`（borrow/return）及带时区的 `occurred_at`。借书还需 reader、copy；还书还需 loan、branch。同一离线事件跨管理员、跨入口重试仍使用相同 UUID、时间及内容。返回 HTTP 200 仅代表批次处理完毕，必须检查每项 status。普通读者不能使用该入口代替在线借还书。

验证码辅助入口继续使用 `GET /api/v1/auth/captcha/`、`POST /api/v1/auth/sms-code/`。生产环境的短信、实名供应商接入限制维持现有配置。

## 使用与验证

导入 [postman_collection.json](postman_collection.json)，填写 phone、password 及实际馆藏、网点 ID。登录请求自动保存令牌；借书请求自动保存 loan_id。首次请求自动生成各操作幂等键，开始下一笔交易前清空相应 key。验证码图片需人工查看后填写 captcha_answer。离线请求需管理员令牌，并填写实际发生时间，不能把时间在每次重试时重新生成。

[openapi.yaml](openapi.yaml) 是接口导出，兼容副本为 `backend/openapi.yaml`。在线文档位于 `/api/docs/`，原始模式位于 `/api/schema/`。修改接口后在项目根目录执行：

```powershell
.\.venv\Scripts\python.exe backend/manage.py test library.tests --verbosity 1
.\.venv\Scripts\python.exe backend/manage.py check
.\.venv\Scripts\python.exe backend/manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe backend/manage.py spectacular --file backend/openapi.yaml --validate --fail-on-warn
Copy-Item backend/openapi.yaml docs/api/openapi.yaml
```

王恒新增的接口契约测试在 `test_auth.py`、`test_circulation.py`；原有回归测试继续保留。当前本地测试使用 SQLite，不能替代 MySQL 的并发锁验证和真实设备联调。部署沿用根目录 `compose.yaml`、`backend/Dockerfile`、`deploy/nginx.conf`，避免维护重复部署配置。
