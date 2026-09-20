#!/usr/bin/env python3
"""在后端数据库中创建模拟器设备，并自动写入 config.yaml。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import yaml

BACKEND = Path(__file__).resolve().parents[1] / 'backend'
CONFIG = Path(__file__).resolve().parent / 'config.yaml'
sys.path.insert(0, str(BACKEND))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django  # noqa: E402

django.setup()

from library.models import Branch, Device  # noqa: E402

SPECS = {
    'gate': ('模拟门禁', 'gate'),
    'smoke': ('模拟烟感', 'smoke'),
    'rfid': ('模拟RFID通道', 'rfid'),
}


def main():
    branch, _ = Branch.objects.get_or_create(name='中心城市书房', defaults={'address': '示例路 1 号'})
    mapping: dict[str, dict] = {}
    for key, (name, kind) in SPECS.items():
        dev, created = Device.objects.get_or_create(branch=branch, name=name, defaults={'kind': kind})
        mapping[key] = {'branch_id': branch.pk, 'device_id': dev.pk, 'name': name}
        print(f"{'创建' if created else '已存在'}: {key} id={dev.pk} branch={branch.pk}")

    cfg = {}
    if CONFIG.exists():
        with CONFIG.open(encoding='utf-8') as f:
            cfg = yaml.safe_load(f) or {}
    cfg.setdefault('mqtt', {'host': 'localhost', 'port': 1883, 'username': '', 'password': ''})
    cfg['devices'] = mapping
    cfg.setdefault('simulation', {'heartbeat_interval_seconds': 30})
    with CONFIG.open('w', encoding='utf-8') as f:
        yaml.safe_dump(cfg, f, allow_unicode=True, sort_keys=False)
    print(f'\n已更新 {CONFIG.name}，可直接运行 simulator.py')


if __name__ == '__main__':
    main()
