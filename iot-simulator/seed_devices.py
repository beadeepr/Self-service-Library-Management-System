#!/usr/bin/env python3
"""在后端数据库中创建模拟器所需的设备（需配置 DJANGO_SETTINGS_MODULE）。"""

import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / 'backend'
sys.path.insert(0, str(BACKEND))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django  # noqa: E402

django.setup()

from library.models import Branch, Device  # noqa: E402


def main():
    branch, _ = Branch.objects.get_or_create(name='中心城市书房', defaults={'address': '示例路 1 号'})
    specs = [
        ('模拟门禁', 'gate'),
        ('模拟烟感', 'smoke'),
        ('模拟RFID通道', 'rfid'),
    ]
    for name, kind in specs:
        dev, created = Device.objects.get_or_create(branch=branch, name=name, defaults={'kind': kind})
        action = '创建' if created else '已存在'
        print(f'{action}: id={dev.pk} branch={branch.pk} kind={kind} name={name}')
    print('\n请将以上 id 填入 iot-simulator/config.yaml 的 devices 段。')


if __name__ == '__main__':
    main()
