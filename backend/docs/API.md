# 后端接口说明与需求映射

## 通用约定

- 前缀 `/api/v1/`，JSON UTF-8，时间采用 ISO-8601，金额为十进制定点字符串。
- JSON 统一响应：`{code, message, data, request_id}`，成功 code=0，request_id 同时出现在 X-Request-ID 响应头。客户端必须检查 code，不能仅以 HTTP 200 判断业务成功。
- 列表分页放在 data 中：`{count, next, previous, results}`，默认每页 20 条，使用 `?page=2`。
- 错误详情放在 data 中：`{"detail":"原因"}` 或字段到错误消息数组的映射。库存不可借按架构约定返回 HTTP 200 + code=4001；未认证 401、无权限 403、不存在或不可见 404、其他非法输入/规则校验 400、数据库冲突 409，对应 code 为 HTTP 状态码 × 100。CSV、OpenAPI 文件和 HTTP 204 无 JSON 包装。
- 角色：读者 `reader`、管理员 `admin`、运维 `operator`。读者只可查询自己的借阅、罚款、支付、信用、押金和入馆记录；运营人员不具备读者财务与角色管理权限。
- 标记 **幂等** 的操作必须传 `Idempotency-Key`，最长 128 字符；相同用户的同一键必须用于相同接口和请求体。重试返回原结果，不重复扣款、借书或入库。
- 所有写入字段以 Swagger 为准；库存状态、罚款累计、支付状态等不能通过普通 PATCH 随意更改。
- 图书 `Book` 为书目，`Copy` 为可流通的物理副本。库存数量由副本统计，避免维护两份数量。
- 图书状态：`available / loaned / reserved / processing / transit / withdrawn / lost`。
- 基础 CRUD 指 GET 列表/详情、POST 创建、PUT/PATCH 修改、DELETE 删除。有关联记录时删除会拒绝；流通、支付、信用、审计等记录不提供删除接口。

## 认证与读者

| 方法与路径 | 权限 | 用途 |
| --- | --- | --- |
| GET auth/captcha/ | 公开 | 返回图形验证码 data URI，有效 5 分钟 |
| POST auth/sms-code/ | 公开 | 校验图形验证码后发送注册、登录、换号验证码 |
| POST auth/register/ | 公开 | phone、code、password、可选 first_name；注册只能产生 reader |
| POST auth/login/ | 公开 | phone、password；返回 access/refresh/role |
| POST auth/sms-login/ | 公开 | phone、code |
| POST auth/qr-challenge/ | 公开 | 生成扫码 token 和仅供发起端持有的 poll_secret |
| POST auth/qr-confirm/ | 登录用户 | 扫码端确认 token |
| POST auth/qr-poll/ | 持有 token/poll_secret | 等待确认或一次性兑换登录令牌 |
| POST auth/refresh/ | refresh 令牌 | 换取令牌，刷新令牌轮换且旧令牌进入黑名单 |
| POST auth/logout/ | refresh 令牌 | 吊销刷新令牌；已签发 access 到期前仍有效 |
| GET/PATCH readers/me/ | 登录用户 | 查看或修改昵称、头像 URL、联系方式 |
| POST readers/password/ | 登录用户 | old_password/new_password；更改后旧访问令牌失效 |
| POST readers/phone/ | 登录用户 | 新手机号及对应换号验证码 |
| POST readers/verify-identity/ | 登录用户 | 单独同意后模拟核验 18 位证件，保存 HMAC 摘要而非明文 |
| GET readers/、readers/{id}/ | 管理员 | 读者查询与检索 |
| POST readers/{id}/manage/ | 管理员 | **幂等**：冻结、重置密码、信用增减、押金增减；reason 必填 |
| GET credit-entries/、deposit-entries/ | 本人/管理员 | 信用和押金流水 |
| GET/POST consents/ | 本人 | 追加同意/撤回记录，purpose=identity 或 biometric |

连续 5 次密码错误锁定 15 分钟；短信验证码 5 分钟有效、最多尝试 5 次、一次使用，60 秒内不可重复发送。模拟模式的验证码响应包含 `simulation_code`，真实环境不提供模拟发送。QR 的 poll_secret 不应编码进展示给扫码者的二维码。角色变更只允许超级管理员执行。

信用等级为 normal/restricted/untrusted；默认最低借阅信用为 60，低于 40 标记失信，冻结状态标记受限。借阅资格同时受欠费、逾期、冻结等规则限制。实名认证提升的借阅上限与借期可单独配置。实名认证只进行格式与唯一性模拟，不代表已完成公安或第三方核验。

## 馆藏与流通

| 方法与路径 | 权限 | 用途 |
| --- | --- | --- |
| branches/、categories/、books/ | 公开读、管理员写 | 网点、分类树、书目 CRUD |
| GET books/?search=关键词 | 公开 | ISBN/书名/作者/分类号/索书号组合模糊检索 |
| GET books/?isbn=...&category=...&author=... | 公开 | 精确过滤；返回 total_count、available_count |
| POST books/{id}/intake/ | 管理员 | **幂等**：branch、quantity(1~500)、shelf；创建副本并生成唯一 RFID |
| GET copies/、copies/{id}/ | 公开 | 按 book/branch/status/rfid/shelf 查询馆藏位置 |
| POST copies/{id}/set-status/ | 管理员 | 下架、报损或转待处理，需 reason |
| POST copies/{id}/disinfect/ | 管理员/运维 | 消毒完成登记 |
| POST copies/{id}/shelve/ | 管理员/运维 | shelf；待处理副本上架并分配下一位预约者 |
| GET loans/、loans/{id}/ | 本人/管理员 | 借阅历史；returned_at__isnull=true 查当前借阅，due_at__lt 查逾期 |
| POST loans/borrow/ | 本人/管理员 | **幂等**：copy；管理员可指定 reader 手工借书 |
| POST loans/{id}/return/ | 本人/管理员 | **幂等**：branch、可选 damaged；允许跨馆归还 |
| POST loans/{id}/renew/ | 本人/管理员 | **幂等**：续借，校验逾期、预约队列、次数、欠费 |
| POST loans/{id}/remind/ | 管理员 | 发送站内催还通知 |
| GET reservations/、reservations/{id}/ | 本人/管理员 | 查看预约 |
| POST reservations/ | 登录用户 | **幂等**：book、branch；按选定取书馆的借出/可借情况判断 |
| POST reservations/{id}/cancel/ | 本人/管理员 | **幂等**：取消并释放保留副本 |
| POST reservations/{id}/collect/ | 本人/管理员 | **幂等**：预约取书并生成借阅记录 |
| GET fines/、payments/ | 本人/管理员 | 罚款和支付订单 |
| POST fines/{id}/adjust/ | 管理员 | **幂等**：人工复核金额/已计费天数，reason 必填，金额不能低于已付款 |
| POST payments/ | 本人/管理员 | **幂等**：fine；按未付余额创建订单 |
| POST payments/{id}/simulate/ | 本人/管理员 | 模拟缴费，重复调用不重复入账 |
| POST payments/{id}/offline/ | 管理员 | 登记线下缴费 |
| POST payments/callback/ | HMAC 签名 | 验签、金额校验、5 分钟时间窗、重复回调幂等 |
| GET/PATCH rules/{id}/、GET rules/ | 管理员 | 借期、上限、罚款费率、预约保留、节假日、留存期等规则 |

借还、续借、预约、支付、调拨在数据库事务中执行，锁定关键读者/书目/副本记录；有效借阅另有唯一 active_copy 约束。SQLite 不实现 MySQL 的行锁语义。

借阅默认上限 5 册、借期 30 天；实名后上限 10 册、借期 45 天。默认最多续借 1 次、预约 5 册、到馆保留 2 天、逾期每天 0.50 元，不足一天按一天。节假日配置使新借阅/续借的应还日顺延至非节假日。费率调整作用于后续新增计费天数，不改写已经计费的金额。

归还默认先进入 `processing`，消毒并上架后转 `available` 或 `reserved`。这是 FR-13 与 FR-17 的衔接选择，可通过 `disinfection_required=false` 直接释放正常归还副本。损坏归还始终待处理；管理员可处理后登记上架或报损。跨馆归还的预约按实际到馆地点匹配，其他馆的等候预约需通过配送调配满足。

支付签名：`HMAC-SHA256(PAYMENT_SIGNING_KEY, reference + "|" + amount + "|" + timestamp)`，amount 使用两位小数字符串，timestamp 为 Unix 秒。服务端不向读者返回签名密钥。未安装真实支付供应商适配，模拟接口仅开发演示可用。

## 设备、安全和运营

| 方法与路径 | 权限 | 用途 |
| --- | --- | --- |
| devices/ | 管理员只读、运维可写 | 设备台账 CRUD，online/shadow 由事件更新 |
| POST devices/{id}/events/ | 运维 | 上传设备事件；event_id 去重 |
| POST devices/{id}/command/ | 运维 | **幂等**：开关机、重启、门禁解锁、喊话；reason 必填 |
| GET device-events/、device-commands/ | 管理员/运维 | 遥测、设备影子来源和命令执行台账 |
| GET alerts/ | 管理员/运维 | 分级告警查询 |
| POST alerts/{id}/transition/ | 管理员/运维 | open → acknowledged → resolved，关闭需 resolution |
| POST visits/access/ | 本人/管理员 | **幂等**：branch、direction=enter/exit、method=qr/card/face |
| GET visits/ | 本人/管理员 | 进出馆历史 |
| GET branches/{id}/occupancy/ | 公开 | 在馆人数、容量、按人数估算的空闲座位数 |
| POST visits/help/ | 登录用户 | branch、message；发送紧急求助告警 |
| GET/POST transfers/ | 管理员/运维 | **创建幂等**：copy、destination、route、schedule |
| POST transfers/{id}/transition/ | 管理员/运维 | **幂等**：ship/receive/cancel/redirect/return |
| GET/POST/PATCH work-orders/ | 管理员/运维 | 技术、书籍、卫生、安全工单；分配负责人和截止时间 |
| POST work-orders/{id}/transition/ | 管理员/运维 | open → in_progress → completed → reviewed；复核仅管理员 |
| GET/POST inventories/ | 管理员/运维 | RFID 手工盘点，返回 missing/surplus/misplaced |
| operations/ | 管理员/运维 | 职责、绩效、工时、成本、应急预案、演练、视频索引 CRUD |
| GET audit-logs/ | 管理员 | 不可通过 API 修改的操作审计 |
| POST offline/sync/ | 管理员 | 批量离线交易补传，每批 1~100 条，逐条返回 applied/conflict |

网点开闭时间相同表示全天开放，支持跨午夜开放区间；入馆检查信用、冻结、人数上限和重复入馆。门禁身份方式采用已鉴权读者与模拟设备语义；人脸方式还须最新 biometric 同意。正常出馆不受欠费或信用限制，冻结账号由管理员出馆补录或应急解锁处理。

设备未借出 RFID 离馆触发防盗告警；烟感触发严重告警、维修任务与门禁联动命令记录。MQTT 与 REST 使用同一事件处理服务。真实设备控制需接入命令消费/执行回执适配器；`pending` 不等于实际执行完成。

`operations.kind` 取值：`responsibility / performance / labor / cost / emergency_plan / drill / video`。使用 `details` 记录岗位职责、协同界面、绩效指标、服务费计算依据、设施与演练结果等扩展数据；`amount`、`hours`、`occurred_on` 支持年度成本和工时汇总。视频仅登记索引与有效期，不上传或分析真实视频，视频记录必须提供 expires_at。

离线补传格式：

```json
{
  "transactions": [
    {
      "event_id": "bf5c38f4-a110-4486-bfa6-87a02cdf3833",
      "kind": "borrow",
      "reader": 2,
      "copy": 1,
      "occurred_at": "2026-09-20T12:00:00+08:00"
    }
  ]
}
```

返回记录使用 `kind=return`、`loan`、`branch`。同一上传账号重试必须保持 event_id 和内容不变。借阅与归还时间采用 occurred_at；补传仍重新检查服务器库存/资格，不覆盖冲突记录。离线归还早于已经计费日期时返回复核冲突，管理员先调整罚款再重传。浏览器或终端的离线本地队列、离线身份授权凭证属于客户端部分，本后端提供补传与冲突处理接口。

## 消息、统计、集成和扩展

| 方法与路径 | 权限 | 用途 |
| --- | --- | --- |
| GET notifications/ | 本人 | 预约到馆、到期、逾期、设备告警站内通知 |
| POST notifications/{id}/read/ | 本人 | 标记已读 |
| announcements/ | 公开读、管理员写 | 公告 CRUD，普通读者仅见 published 公告 |
| GET reports/summary/ | 管理员/运维 | 馆藏/分类、借阅趋势、热门图书、读者活跃、客流、设备、收入、工时和成本 |
| GET reports/export/ | 管理员 | 馆藏 CSV 导出并审计，防止电子表格公式注入 |
| POST integrations/catalogue-import/ | 管理员 | **幂等**：按 ISBN 批量 upsert 标准化书目，不直接伪造物理库存 |
| GET integrations/capabilities/ | 管理员 | 返回标准接口地址和扩展能力状态 |
| activities/ | 公开读、管理员写 | 活动发布 CRUD |
| POST/DELETE activities/{id}/enroll/ | 本人 | 报名/取消，校验名额和活动开始时间 |

馆内读者库与流通系统对接复用 readers/loans/copies 的 v1 JSON/JWT 标准接口。外部平台协议、实际第三方连接和身份映射需按对接方规范适配，不声称已接入某个真实馆务系统。

普通行为数据保留期默认 180 天；任务清理过期通知、设备事件、结束的进出馆记录、已结束且无未清款项的借阅记录等。涉及财务的罚款/支付/审计按独立 financial_retention_days（默认 1825 天的演示策略）保留，未结清款项不自动删除。视频按各记录 expires_at 清理索引，外部视频文件须由存储服务按同一策略删除。此机制是可配置技术能力，不代表已完成具体机构的法律合规审查。

## 最小借还调用示例

```http
POST /api/v1/auth/login/
Content-Type: application/json

{"phone":"13800000002","password":"Library-Demo-2026!"}
```

```http
POST /api/v1/loans/borrow/
Authorization: Bearer <access>
Idempotency-Key: demo-borrow-001
Content-Type: application/json

{"copy":1}
```

登录令牌位于 `data.access`；借书结果位于 `data`，结构为 `{id, copy, due_at}`，其中 id 为借阅编号：

```http
POST /api/v1/loans/1/return/
Authorization: Bearer <access>
Idempotency-Key: demo-return-001
Content-Type: application/json

{"branch":1,"damaged":false}
```

管理员/运维随后调用副本的 `disinfect/` 和 `shelve/` 完成消毒上架。

## 需求对应与边界

| 需求 | 对应接口或机制 | 实施说明 |
| --- | --- | --- |
| FR-01~04 | auth、readers/me/password/phone/verify-identity | 验证码/账号锁定、JWT、扫码确认；短信和实名为模拟 |
| FR-05~06 | rules、credit-entries、readers/manage、audit-logs | 信用等级、角色隔离、审计 |
| FR-07~11 | books/categories/copies、intake、reports | 书目/副本分离、RFID、检索统计 |
| FR-12~14 | transfers、disinfect/shelve、inventories、设备事件 | 配送、消毒、上架、盘点、防盗；周期扫描由设备上报 |
| FR-15 | copies 的 branch/book.category 与待处理流程 | 进阶：自动分拣设备执行与准确率统计待适配 |
| FR-16~20 | loans、借还服务、管理员代办、罚款人工复核 | 事务与幂等、借还/续借、历史、异常兜底 |
| FR-21~23 | reservations、notifications、maintenance | 队列、保留期、到馆通知；站内信可用，外部通知通道待接 |
| FR-24~26 | fines/payments、credit-entries、maintenance | 分日计费、模拟/线下支付、签名回调、信用流水 |
| FR-27~28 | visits/access、branches/occupancy | 门禁鉴权、人数；空闲座位为人数估算，未连接座位传感器 |
| FR-29 | devices/events/shadow | 进阶：环境遥测已支持，阈值控制策略与自动节能待扩展 |
| FR-30~33 | alerts、visits/help、device-commands、work-orders、operations/video | 仿真安防信号、远程处置、烟感联动和现场工单 |
| FR-34 | offline/sync | 后端补传、重试与冲突返回；客户端本地缓存由前端实现 |
| FR-35~36 | transfers、copies/shelve、work-orders | 验收、改派/退回、维修结果与复核 |
| FR-37~38 | operations、reports | 职责/绩效数据、工时、年度成本；具体服务费公式由运营方配置数据 |
| FR-39 | activities、enroll | 已提供活动发布和容量受控报名 |
| FR-40~43 | loans/readers/manage/copies/transfers/devices | 后台查询、代办、冻结、押金与设备监控 |
| FR-44~47 | reports、notifications、announcements、rules | 运营报表、公告通知、规则配置和导出 |
| FR-48 | integrations/catalogue-import、capabilities、v1 标准资源接口 | 馆内集成契约与书目导入；真实系统适配需提供协议 |
| FR-49~51 | integrations/capabilities 和模块服务边界 | 进阶：城市平台、外部信用借还、座位预约保留扩展声明 |
| FR-52~54 | branches/evaluation/area/zones/seats/services/opening_time | 选址人口/半径等数据录入、功能分区、开放公示与客流 |
| FR-55 | branches/accessibility、中文 API 错误消息 | 后端提供无障碍设施说明；大字体等为前端职责 |
| FR-56 | operations/emergency_plan/drill、烟感联动 | 应急制度、演练记录、设备处置台账 |
| FR-57 | consents、摘要存储、权限、审计、purge_expired | 独立同意、访问记录、分类保留与清理；不采集原始人脸 |

本次产物是可运行的后端接口与演示能力，不包括 Vue 页面、真实硬件大规模部署或真实生产支付。NFR 中的性能、可用性、主备切换、生产安全评估需在目标 MySQL/Redis/MQTT/网关环境验证；本仓库的功能测试不能替代这些验收。

超级管理员拥有运维权限，普通 admin 角色按架构矩阵仅可查看设备。密码使用 bcrypt-SHA256，兼容已有 PBKDF2 记录并在登录时升级。手机号、昵称、联系方式使用 AES-SIV 认证加密存储；手机号/昵称仅支持精确过滤，不提供密文字段模糊查询。管理员查看其他读者的手机号默认脱敏。证件只保存唯一性校验所需的 HMAC 摘要，不保存原件或生物特征。

幂等结果保留至 financial_retention_days，超过保留期不保证旧请求键仍可重放。借还成功会在同一事务保存领域事件 outbox，并产生站内通知；Celery 将事件按 QoS 1 发布到 `library/{siteId}/domain/event`，接收方按 event_id 去重。MQTT 故障保留待发布事件，不回滚已提交借还。

设备命令发布到 `library/{siteId}/device/{deviceId}/command`，签名为 `HMAC-SHA256(DEVICE_SIGNING_KEY, command_id|device_id|command|timestamp|reason)`。接入设备必须验证签名、命令时间窗并持久化已执行 command_id 防重放；模拟环境只记录和发布带 simulation=true 的命令，不声称真实设备已执行。
