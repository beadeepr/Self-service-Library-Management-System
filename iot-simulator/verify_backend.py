#!/usr/bin/env python3
"""不依赖 MQTT broker：直接验证后端 ingest 与模拟器事件格式一致。"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / 'backend'
sys.path.insert(0, str(BACKEND))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django  # noqa: E402

django.setup()

from library.models import Alert, Branch, Device, DeviceCommand, DeviceEvent  # noqa: E402
from library.services import operations  # noqa: E402


def main() -> int:
    branch, _ = Branch.objects.get_or_create(name='中心城市书房', defaults={'address': '示例路 1 号'})
    gate, _ = Device.objects.get_or_create(branch=branch, name='模拟门禁', defaults={'kind': 'gate'})
    smoke, _ = Device.objects.get_or_create(branch=branch, name='模拟烟感', defaults={'kind': 'smoke'})

    before_alerts = Alert.objects.count()
    before_cmds = DeviceCommand.objects.filter(device=gate, command='unlock').count()
    event_id = uuid.uuid4()

    result = operations.ingest(None, smoke.pk, event_id, 'smoke', {'message': 'verify_backend 自检'})
    assert not result['duplicate'], '事件应首次写入'

    after_alerts = Alert.objects.count()
    after_cmds = DeviceCommand.objects.filter(device=gate, command='unlock').count()
    events = DeviceEvent.objects.filter(event_id=event_id).count()

    checks = [
        (events == 1, 'DeviceEvent 已写入'),
        (after_alerts > before_alerts, 'Alert 已生成'),
        (after_cmds > before_cmds, '门禁 unlock 命令已生成'),
    ]
    ok = True
    for passed, msg in checks:
        status = 'OK' if passed else 'FAIL'
        print(f'{status}: {msg}')
        ok = ok and passed

    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
