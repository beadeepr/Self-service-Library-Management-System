# 无人值守图书馆系统 · 前端

Vue 3 + TypeScript 单页应用，承载三端界面，通过 REST 对接同仓库的 Django 后端（[`../backend/`](../backend/)），
不引入独立 BFF，也没有前端自建的服务端。

| 端 | 路由前缀 | 主要能力 |
| --- | --- | --- |
| 读者 Web | `/reader` | 注册登录、图书检索、详情、我的借阅与续借、预约与取书、罚款缴纳、个人中心 |
| 自助终端 | `/kiosk` | 读者签到、三步借书、三步还书（支持跨馆归还）、门禁进/出馆、一键求助 |
| 管理后台 | `/admin` | 运营大屏、图书与馆藏（入库/副本流转）、读者管理、借还兜底、设备状态、告警中心 |

## 技术栈

Vue 3.5 · Vite 8 · TypeScript 5.9 · Element Plus 2.14 · Pinia 4 · Vue Router 5 · Axios 1.x

运行时需要 Node ≥ 20（本项目在 Node 24 上开发与验证，Docker 镜像使用 `node:24-alpine`）。

未引入图表库：运营大屏的条形与柱状图用 CSS 实现（见 `src/components/VizBarList.vue`、`VizColumnChart.vue`）。

> TypeScript 固定在 `~5.9.3`：`vue-tsc@3.3.11` 在 TypeScript 7 下会直接崩溃（TS 7 不再导出 `./lib/tsc`）。
> 升级 TS 前请先确认 vue-tsc 已支持。

## 快速开始（本地开发）

**前置**：后端已在 `127.0.0.1:8000` 运行，启动方式见 [`../backend/README.md`](../backend/README.md)。

```bash
cd frontend
npm install
npm run dev
```

打开 <http://127.0.0.1:5173>。开发服务器把 `/api` 与 `/health` 代理到 `http://127.0.0.1:8000`，
因此前端代码一律用同源相对路径，不区分环境。

后端不在默认地址时：

```bash
# bash / Git Bash
VITE_BACKEND_ORIGIN=http://192.168.1.10:8000 npm run dev
# PowerShell
$env:VITE_BACKEND_ORIGIN='http://192.168.1.10:8000'; npm run dev
```

### 初始化演示数据（在后端侧执行）

```bash
python manage.py seed_demo --password 'Library-Demo-2026!'
python manage.py seed_demo_showcase --password 'Reader-Demo-2026!'
```

- `seed_demo`：最小可运行数据（3 个账号、2 个网点、1 本书 3 册、1 台设备）。
- `seed_demo_showcase`：演示所需的业务状态（第二本书、逾期借阅与罚款、可预约状态、
  进馆记录、告警与工单、公告）。可重复执行，不会重复造数据。

## 演示账号

| 手机号 | 口令 | 角色 | 登录后落点 |
| --- | --- | --- | --- |
| `13800000001` | `Library-Demo-2026!` | 管理员 | `/admin/dashboard` |
| `13800000002` | `Library-Demo-2026!` | 读者（主演示账号） | `/reader/home` |
| `13800000003` | `Library-Demo-2026!` | 运维 | `/admin/dashboard`（仅 4 项菜单） |
| `13480588246` | `Reader-Demo-2026!` | 读者（逾期演示） | `/reader/home`，带 1 笔逾期与未缴罚款 |
| `13380588246` | `Reader-Demo-2026!` | 读者（持有副本） | `/reader/home` |

登录页提供「演示账号」一键填入（手机号 + 演示口令），便于现场演示。

## 答辩演示脚本

建议按 读者 Web → 自助终端 → 管理后台 的顺序，每段 1~2 分钟。

**1. 读者 Web（主账号 `13800000002`）**
- 首页公告与检索入口 → 检索「数据」，进入《数据结构与算法分析》详情
- 详情显示「暂无可借」，点「预约」→ 选社区分馆 → 预约成功 → 我的预约显示「排队中」
- 我的借阅 / 个人中心（信用、押金、实名状态）

**2. 逾期与罚款（`13480588246`）**
- 我的借阅：「已逾期 11 天」；罚款页：未缴 ¥5.50（11 天 × 0.50），提交缴纳后转入已缴记录
- 说明：未缴清罚款与逾期未还会阻止继续借阅，缴清并归还后才恢复资格

**3. 自助终端（`13800000002` 签到）**
- 签到后进「借书」：识别 → 确认 → 借阅成功（展示应还日期）
- 「还书」：识别 → 确认（可选归还网点与损坏）→ 归还成功，副本进入待处理
- 「门禁通行」：进馆/出馆、在馆人数；一键求助会生成告警

**4. 管理后台（`13800000001`）**
- 运营大屏：在馆人数、设备在线、开放告警、逾期借阅、馆藏分布、借阅趋势
- 图书与馆藏：新增书目 → 入库生成副本 → 副本抽屉里消毒/上架/下架
- 借还管理：代办借书、催还、归还（异常兜底）
- 读者管理：冻结、信用/押金调整（理由必填，记入审计）
- 设备状态 / 告警中心：设备影子、指令台账；告警「确认 → 关闭」（关闭需处理结论）

**预约闭环的完整演法**：主账号预约后，由管理员在「图书与馆藏 → 副本」把该书某一册
消毒并上架，副本上架时后端会把等候中的预约置为「已到馆待取」并发送到馆通知；
主账号刷新「我的预约」即可取书，生成借阅记录。

## 与后端的约定（改代码前必读）

- **接口前缀** `/api/v1`。少数兼容别名（如 `/api/books/search/`）也存在，但新代码统一用 `/api/v1`。
- **统一信封** `{code, message, data, request_id}`，成功 `code=0`。
  **库存不可借返回 HTTP 200 + `code=4001`** —— 必须判 `code`，不能只看 HTTP 状态。
  分页数据在 `data.results`，后端固定 20 条/页且不提供 `page_size`。
- **幂等**：借书、还书、续借、预约/取消/取书、支付下单、门禁读卡、读者管理、入库都要求
  `Idempotency-Key`。同一笔交易重试要复用同一个键与相同请求体，新交易换新键。
  统一走 `src/api/client.ts` 的 `postIdempotent()`；各页面的做法是把键存在交易级状态里，
  失败保留、成功后清除。
- **令牌**：`Authorization: Bearer <access>`；access 30 分钟。刷新接口会**轮换 refresh**，
  必须把响应里的新 refresh 覆盖写回（见 `src/api/session.ts`）。刷新失败时整页跳回登录页，
  确保清空内存态。
- **错误文案**：后端校验错误可能是嵌套结构（如 `{"password":{"password":[...]}}`），
  `client.ts` 的 `describeError` 会递归取第一条可读原因。
- **角色边界在后端**：路由守卫只负责把用户导到能用的一端，不作为安全边界。
  运维在图书页是「可消毒上架、其余只读」，借还管理与读者管理仅管理员可见。

## 目录结构

```
frontend/
├── index.html
├── vite.config.ts          # 代理 /api、/health；@ → src
├── tsconfig.json           # 应用代码（不设 baseUrl，兼容 TS 7）
├── tsconfig.node.json      # vite.config.ts 的类型检查
└── src/
    ├── main.ts             # Pinia → Router → Element Plus 的安装顺序有依赖
    ├── api/                # client（信封/刷新/幂等）、session、各业务接口
    ├── stores/             # auth（登录态）、reader（当前读者资料）
    ├── router/index.ts     # 三端路由与角色守卫
    ├── views/reader|kiosk|admin
    ├── components/         # 图书卡、借阅表、验证码输入、可视化条形等
    ├── composables/        # useSmsCode、useCatalog（对照数据缓存）、useOfflineQueue
    ├── kiosk/offline-queue.ts
    ├── utils/              # 校验、格式化（金额/日期/逾期天数）
    └── styles/             # base.css（设计令牌）、kiosk.css（大字号无障碍）
```

## Docker 部署

前端以独立服务加入根目录 [`../compose.yaml`](../compose.yaml)，镜像定义在
[`../deploy/frontend/`](../deploy/frontend/)。以下步骤等价于在仓库根目录执行 `./start.sh`
（或 `.\start.ps1`），手工执行时按顺序：

```bash
docker compose up -d mysql redis emqx
docker compose build
docker compose run --rm api python manage.py migrate
docker compose run --rm api python manage.py collectstatic --noinput
docker compose run --rm api python manage.py seed_demo --password 'Library-Demo-2026!'
docker compose run --rm api python manage.py seed_demo_showcase --password 'Reader-Demo-2026!'
docker compose up -d
```

| 入口 | 用途 |
| --- | --- |
| <http://127.0.0.1:8081> | **三端界面**（答辩用这个） |
| <http://127.0.0.1:8080> | API 与 Django Admin（`/admin/`，注意带斜杠） |
| <http://127.0.0.1:8000> | 直连 API / Swagger |

镜像自带 nginx：托管 SPA、提供 `/admin/books` 这类前端路由的刷新回退，并把 `/api`、`/health`
同源代理到 `api:8000`（因此不涉及跨域）。构建上下文必须是**仓库根目录**，原因见 Dockerfile 顶部注释。

## 验证

```bash
npm run typecheck   # vue-tsc（应用）+ tsc（vite 配置）
npm run build       # 生产构建
npm run preview     # 预览构建产物（已配置代理，端口 4173）
```

## 已知限制与注意事项

- **登录页硬编码了演示口令**（`Library-Demo-2026!`，见 `views/reader/LoginView.vue`），
  仅为课程演示的「一键填入」方便。正式使用前应删除该常量与演示账号区块。
- **离线补传为演示能力**：`src/kiosk/offline-queue.ts` 实现了 IndexedDB 队列、幂等去重、冲突状态回写
  与网络恢复后的自动补传；后端允许读者补传本人交易，管理员仍可代传。
  离线登录授权凭证尚未实现，断网时需保持原会话未过期。补传仍由服务端重新校验库存与资格。
- **Element Plus 为全量引入**，厂商 chunk 约 1 MB（gzip ≈ 350 KB），构建时会提示 chunk 过大。
  若在意体积，可改为按需引入。
- **大屏不引入图表库**，图形为 CSS 实现；趋势数据不足 3 天时降级为列表，避免「一两根柱子」被误读为趋势。
- 前端没有自己的环境变量文件：只有 `VITE_BACKEND_ORIGIN` 影响开发代理，构建产物中的 API 地址恒为同源。
- 若登录后立刻被登出，通常是后端更换了 `FIELD_ENCRYPTION_KEY`（加密字段无法解密）或令牌已失效；
  前者会让登录直接失败，且**已有数据无法恢复**，只能恢复原密钥。
