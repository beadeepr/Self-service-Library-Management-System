#!/usr/bin/env python3
"""无人值守图书馆 — 交互式 MQTT 设备模拟器（成员 C）

协议对齐 backend：
  - 发布：library/{branch_id}/device/{device_id}/event|telemetry|status
  - 订阅：library/+/device/+/command（接收门禁 unlock 等指令）
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import threading
import time
import uuid
from pathlib import Path

import yaml

try:
    import paho.mqtt.client as mqtt
except ImportError:
    print('请先安装: pip install -r requirements.txt', file=sys.stderr)
    sys.exit(1)

from lib.envelope import event_envelope
from lib.topics import command_topic, device_topic

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger('iot-simulator')


def load_config(path: Path) -> dict:
    with path.open(encoding='utf-8') as f:
        return yaml.safe_load(f)


def publish_event(client: mqtt.Client, branch_id: int, device_id: int, kind: str, payload: dict | None = None) -> None:
    envelope = event_envelope(kind, payload)
    topic = device_topic(branch_id, device_id, 'event')
    msg = client.publish(topic, json.dumps(envelope), qos=1)
    msg.wait_for_publish(timeout=10)
    logger.info('发布 %s -> %s', topic, envelope)


def publish_telemetry(client: mqtt.Client, branch_id: int, device_id: int, payload: dict) -> None:
    topic = device_topic(branch_id, device_id, 'telemetry')
    msg = client.publish(topic, json.dumps(payload), qos=0)
    msg.wait_for_publish(timeout=10)
    logger.info('遥测 %s -> %s', topic, payload)


def on_command(client, userdata, message):
    try:
        body = json.loads(message.payload.decode())
    except json.JSONDecodeError:
        logger.warning('无效 command 载荷: %s', message.topic)
        return
    logger.info('<<< 收到设备命令 [%s]: %s', message.topic, body)
    cmd = body.get('payload', {}).get('command') or body.get('command')
    if cmd == 'unlock':
        logger.info('>>> 闸机执行 unlock（模拟开门）')


def heartbeat_loop(client, cfg: dict, stop: threading.Event) -> None:
    interval = int(cfg.get('simulation', {}).get('heartbeat_interval_seconds', 30))
    gate = cfg['devices']['gate']
    while not stop.wait(interval):
        publish_event(client, gate['branch_id'], gate['device_id'], 'heartbeat', {'online': True})


def interactive(client: mqtt.Client, cfg: dict) -> None:
    dev = cfg['devices']
    print('\n=== 图书馆 IoT 模拟器（协议 v1）===')
    print('1) 心跳 heartbeat（门禁）')
    print('2) 烟感告警 smoke')
    print('3) RFID 离馆防盗 rfid_exit')
    print('4) 温湿度 telemetry')
    print('5) 紧急求助 help')
    print('6) 盘点 inventory')
    print('7) 设备故障 fault')
    print('q) 退出')
    while True:
        choice = input('\n请选择 > ').strip().lower()
        if choice == '1':
            g = dev['gate']
            publish_event(client, g['branch_id'], g['device_id'], 'heartbeat')
        elif choice == '2':
            s = dev['smoke']
            publish_event(client, s['branch_id'], s['device_id'], 'smoke', {'message': '模拟烟感告警'})
        elif choice == '3':
            r = dev['rfid']
            tags = input('RFID UUID 列表（逗号分隔，留空随机）: ').strip()
            rfids = [t.strip() for t in tags.split(',') if t.strip()] if tags else [str(uuid.uuid4())]
            publish_event(client, r['branch_id'], r['device_id'], 'rfid_exit', {'rfids': rfids})
        elif choice == '4':
            s = dev.get('smoke', dev['gate'])
            publish_telemetry(client, s['branch_id'], s['device_id'],
                              {'temperature': 26.5, 'humidity': 55, 'light': 420})
        elif choice == '5':
            s = dev['smoke']
            publish_event(client, s['branch_id'], s['device_id'], 'help', {'message': '读者按下紧急求助按钮'})
        elif choice == '6':
            r = dev['rfid']
            shelf = input('书架编号 [A-01]: ').strip() or 'A-01'
            tags = input('observed RFID（逗号分隔，留空随机3个）: ').strip()
            observed = [t.strip() for t in tags.split(',') if t.strip()] if tags else [str(uuid.uuid4()) for _ in range(3)]
            publish_event(client, r['branch_id'], r['device_id'], 'inventory', {'shelf': shelf, 'observed': observed})
        elif choice == '7':
            g = dev['gate']
            publish_event(client, g['branch_id'], g['device_id'], 'fault', {'message': '闸机电机异常'})
        elif choice in {'q', 'quit', 'exit'}:
            break
        else:
            print('无效选项')


def main() -> None:
    parser = argparse.ArgumentParser(description='图书馆 MQTT 设备模拟器')
    parser.add_argument('-c', '--config', type=Path, default=Path(__file__).parent / 'config.yaml')
    parser.add_argument('--demo', action='store_true', help='自动发送 smoke + heartbeat 后进入菜单')
    args = parser.parse_args()

    cfg = load_config(args.config)
    mqtt_cfg = cfg['mqtt']
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id='library-iot-simulator')
    if mqtt_cfg.get('username'):
        client.username_pw_set(mqtt_cfg['username'], mqtt_cfg.get('password', ''))
    client.on_message = on_command
    client.connect(mqtt_cfg['host'], int(mqtt_cfg.get('port', 1883)), 60)
    client.subscribe('library/+/device/+/command', qos=1)
    client.loop_start()
    logger.info('已连接 MQTT %s:%s', mqtt_cfg['host'], mqtt_cfg.get('port', 1883))

    stop = threading.Event()
    hb = threading.Thread(target=heartbeat_loop, args=(client, cfg, stop), daemon=True)
    hb.start()

    if args.demo:
        g, s = cfg['devices']['gate'], cfg['devices']['smoke']
        publish_event(client, g['branch_id'], g['device_id'], 'heartbeat')
        publish_event(client, s['branch_id'], s['device_id'], 'smoke', {'message': '演示烟感'})
        time.sleep(0.5)

    try:
        interactive(client, cfg)
    finally:
        stop.set()
        client.loop_stop()
        client.disconnect()


if __name__ == '__main__':
    main()
