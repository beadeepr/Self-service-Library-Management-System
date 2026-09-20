# 无人值守图书馆管理系统

基于需求文档 V2.0 和架构设计的 Django REST 后端，包含读者认证、馆藏、借还、预约、罚款、门禁、设备告警、配送、工单、报表和运营记录接口。

- 后端代码：[`backend/`](backend/)
- 启动与调用说明：[`backend/README.md`](backend/README.md)
- 接口清单、业务约定与需求映射：[`backend/docs/API.md`](backend/docs/API.md)
- OpenAPI 文件：[`backend/openapi.yaml`](backend/openapi.yaml)
- 运行后交互文档：`http://127.0.0.1:8000/api/docs/`

本地可使用 SQLite 演示；Docker 配置提供 MySQL、Redis、Celery 和 EMQX。支付、短信、身份核验及设备控制默认使用显式模拟流程。前端不包含在本次后端接口实现中。

