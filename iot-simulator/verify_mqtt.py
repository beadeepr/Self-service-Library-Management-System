#!/usr/bin/env python3
"""验证 MQTT 连接并发送一条 smoke 测试事件。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

try:
    import paho.mqtt.client as mqtt
except ImportError:
    print('FAIL: 缺少 paho-mqtt', file=sys.stderr)
    sys.exit(1)

from lib.envelope import event_envelope
from lib.topics import device_topic


def main() -> int:
    cfg_path = Path(__file__).parent / 'config.yaml'
    with cfg_path.open(encoding='utf-8') as f:
        cfg = yaml.safe_load(f)
    mqtt_cfg = cfg['mqtt']
    smoke = cfg['devices']['smoke']
    host, port = mqtt_cfg['host'], int(mqtt_cfg.get('port', 1883))

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id='library-verify')
    try:
        client.connect(host, port, 60)
    except Exception as exc:
        print(f'FAIL: 无法连接 MQTT {host}:{port} — {exc}')
        print('提示: docker compose up -d emqx')
        return 1

    client.loop_start()
    topic = device_topic(smoke['branch_id'], smoke['device_id'], 'event')
    payload = event_envelope('smoke', {'message': 'verify_mqtt 自检'})
    result = client.publish(topic, json.dumps(payload), qos=1)
    result.wait_for_publish(timeout=10)
    client.loop_stop()
    client.disconnect()

    if result.is_published():
        print(f'OK: 已发布到 {topic}')
        print('若 mqtt_bridge 在运行，应能在 /api/v1/device-events/ 看到事件')
        return 0
    print('FAIL: 发布超时')
    return 1


if __name__ == '__main__':
    sys.exit(main())
