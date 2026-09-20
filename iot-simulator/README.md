# IoT 设备模拟器（成员 C）

与后端 `mqtt_bridge` / `simulate_device` 使用**相同 MQTT 协议**，提供答辩用的**交互式菜单**，便于演示烟感联动、RFID 防盗、紧急求助等场景。

## 协议

| 方向 | 主题 | 说明 |
| --- | --- | --- |
| 模拟器 → 后端 | `library/{branch_id}/device/{device_id}/event` | 主事件通道 |
| 模拟器 → 后端 | `library/{branch_id}/device/{device_id}/telemetry` | 温湿度等 |
| 后端 → 模拟器 | `library/{branch_id}/device/{device_id}/command` | 如烟感触发的 `unlock` |

事件 JSON：

```json
{
  "event_id": "uuid",
  "kind": "smoke",
  "payload": {"message": "模拟烟感告警"}
}
```

支持 `kind`：`heartbeat`、`smoke`、`rfid_exit`、`help`、`fault`、`inventory`、`security` 等（见 `backend/README.md`）。

## 快速开始

### 1. 启动 EMQX

```powershell
docker compose up -d emqx mysql redis
docker compose up -d api mqtt worker beat
```

或本地仅 EMQX：`docker run -d -p 1883:1883 --name emqx emqx/emqx:5`

### 2. 初始化演示数据

```powershell
.\.venv\Scripts\python.exe backend\manage.py migrate
.\.venv\Scripts\python.exe backend\manage.py seed_demo --password "Library-Demo-2026!"
.\.venv\Scripts\python.exe iot-simulator\seed_devices.py
```

按输出修改 `iot-simulator/config.yaml` 中的 `branch_id` / `device_id`。

### 3. 运行模拟器

```powershell
pip install -r iot-simulator/requirements.txt
python iot-simulator/simulator.py
python iot-simulator/simulator.py --demo
```

### 4. 验证

**无 Docker / 无 EMQX 时**（本地快速自检）：

```powershell
python iot-simulator/verify_backend.py
```

**有 EMQX 时**：

```powershell
python iot-simulator/verify_mqtt.py
python iot-simulator/run_demo.py
```

- 确保 `mqtt` 服务（`mqtt_bridge`）在运行
- API：`GET /api/v1/device-events/`、`GET /api/v1/alerts/`
- 烟感会触发告警 + 门禁 `unlock`（模拟器订阅 `command` 主题可见）

**答辩一键脚本**（需 Docker Desktop 运行）：

```powershell
.\iot-simulator\demo.ps1
```

## 与后端命令对比

| 方式 | 命令 |
| --- | --- |
| 单次 CLI | `python manage.py simulate_device --device 2 --kind smoke --payload "{\"message\":\"test\"}"` |
| 交互模拟器 | `python iot-simulator/simulator.py` |

## 答辩演示建议顺序

1. 启动 compose（含 emqx + mqtt bridge）
2. 运行 `simulator.py --demo`
3. 选项 2 烟感 → 展示告警与闸机 unlock 命令
4. 选项 3 RFID 离馆 → 展示防盗告警
5. 读者端调用 `POST /api/v1/visits/access/` 演示进馆（与 B 联调）
