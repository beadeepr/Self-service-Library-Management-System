# 物联 / 前端联调说明（刘经纬 ↔ 周硕）

后端 API 前缀均为 **`/api/v1/`**（不是 `/api/`）。  
鉴权头：`Authorization: Bearer <access>`  
写操作建议加：`Idempotency-Key: <uuid>`

启动：仓库根目录 `.\start.ps1`（Docker，推荐）或 `.\start.ps1 -Mode local`。  
前端入口见 [`frontend/README.md`](../frontend/README.md)。

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

## 3. IoT 演示（刘经纬负责，答辩另开终端）

```powershell
# 终端 1：主系统（含 EMQX + mqtt_bridge）
.\start.ps1

# 终端 2：模拟器
pip install -r iot-simulator/requirements.txt
python iot-simulator/seed_devices.py
python iot-simulator/run_demo.py
# 或：python iot-simulator/simulator.py
```

烟感 → 告警 + 门禁 `unlock`；管理后台「告警中心」「设备状态」可刷新查看。

## 4. Swagger

Docker：`http://127.0.0.1:8081/api/docs/`；local 模式：`http://127.0.0.1:8000/api/docs/`。  
登录后 Authorize 填入 `Bearer <access>`。
