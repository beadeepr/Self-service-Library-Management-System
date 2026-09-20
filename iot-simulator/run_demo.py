#!/usr/bin/env python3
"""非交互答辩演示：依次发送 heartbeat → smoke → rfid_exit。"""

from __future__ import annotations

import json
import sys
import time
import uuid
from pathlib import Path

import yaml

try:
    import paho.mqtt.client as mqtt
except ImportError:
    print('pip install -r iot-simulator/requirements.txt', file=sys.stderr)
    sys.exit(1)

from lib.envelope import event_envelope
from lib.topics import device_topic


def load_config() -> dict:
    path = Path(__file__).parent / 'config.yaml'
    with path.open(encoding='utf-8') as f:
        return yaml.safe_load(f)


def publish(client: mqtt.Client, branch_id: int, device_id: int, kind: str, payload: dict | None = None) -> None:
    topic = device_topic(branch_id, device_id, 'event')
    body = event_envelope(kind, payload)
    client.publish(topic, json.dumps(body), qos=1).wait_for_publish(timeout=10)
    print(f'[OK] {kind} -> {topic}')


def main() -> None:
    cfg = load_config()
    mqtt_cfg = cfg['mqtt']
    dev = cfg['devices']
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id='library-iot-demo')
    if mqtt_cfg.get('username'):
        client.username_pw_set(mqtt_cfg['username'], mqtt_cfg.get('password', ''))
    client.connect(mqtt_cfg['host'], int(mqtt_cfg.get('port', 1883)), 60)
    client.loop_start()
    time.sleep(0.3)

    g, s, r = dev['gate'], dev['smoke'], dev['rfid']
    publish(client, g['branch_id'], g['device_id'], 'heartbeat')
    time.sleep(0.5)
    publish(client, s['branch_id'], s['device_id'], 'smoke', {'message': '答辩演示：烟感告警'})
    time.sleep(0.5)
    publish(client, r['branch_id'], r['device_id'], 'rfid_exit', {'rfids': [str(uuid.uuid4())]})
    print('\n演示事件已发送。请查看：设备事件 / 告警 / 门禁 unlock 命令。')

    client.loop_stop()
    client.disconnect()


if __name__ == '__main__':
    main()
