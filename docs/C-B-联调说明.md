# 成员 C → 成员 B 联调说明

后端 API 前缀均为 **`/api/v1/`**（不是 `/api/`）。  
鉴权头：`Authorization: Bearer <access>`  
写操作建议加：`Idempotency-Key: <uuid>`

## 1. 门禁 / 在馆（C 负责演示，B 做 Kiosk 页面）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/v1/visits/access/` | 进馆 / 出馆 |
| GET | `/api/v1/visits/` | 进出记录（读者只看自己的） |

**进馆请求体**：

```json
{
  "branch": 1,
  "direction": "enter",
  "method": "card"
}
```

**出馆**：`"direction": "exit"`

**响应 data 含**：`occupancy`（当前在馆人数）

> 读者需先登录：`POST /api/v1/auth/login/`  
> Body: `{"phone":"13800000002","password":"Library-Demo-2026!"}`

## 2. 设备与告警（C 模拟器触发，B 做展示页）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/v1/devices/` | 设备列表（需 staff 角色） |
| GET | `/api/v1/device-events/` | 设备事件日志 |
| GET | `/api/v1/alerts/` | 告警列表 |
| GET | `/api/v1/reports/summary/` | 运营汇总（如有） |

## 3. IoT 演示（C 负责）

```powershell
# 终端 1：Docker
docker compose up -d emqx mysql redis api mqtt worker beat

# 终端 2：初始化 + 模拟器
python backend/manage.py seed_demo --password "Library-Demo-2026!"
python iot-simulator/seed_devices.py
python iot-simulator/run_demo.py
```

烟感事件会触发：告警 + 门禁 `unlock` 命令（模拟器订阅 `command` 主题可看到）。

## 4. Swagger

`http://127.0.0.1:8000/api/docs/` — 登录后 Authorize 填入 `Bearer <access>`。
