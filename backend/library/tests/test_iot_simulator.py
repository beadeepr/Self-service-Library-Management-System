"""成员 C：IoT 模拟器协议与后端 ingest 一致性测试。"""

import uuid
from django.test import TestCase

from library import models as m
from library.services import operations


class IotSimulatorProtocolTests(TestCase):
    def setUp(self):
        self.branch = m.Branch.objects.create(name='IoT测试馆', address='测试')
        self.gate = m.Device.objects.create(branch=self.branch, kind='gate', name='门禁')
        self.smoke = m.Device.objects.create(branch=self.branch, kind='smoke', name='烟感')
        self.rfid = m.Device.objects.create(branch=self.branch, kind='rfid', name='RFID')

    def test_smoke_triggers_unlock_command(self):
        event_id = uuid.uuid4()
        operations.ingest(None, self.smoke.pk, event_id, 'smoke', {'message': '测试'})
        self.assertTrue(m.Alert.objects.filter(kind='smoke').exists())
        self.assertEqual(m.DeviceCommand.objects.filter(device=self.gate, command='unlock').count(), 1)

    def test_rfid_exit_with_invalid_tag_raises_alert(self):
        category = m.Category.objects.create(code='T', name='测试')
        book = m.Book.objects.create(
            isbn='9789999999999', title='书', author='作者', category=category,
            call_number='T/1', price='10.00',
        )
        item = m.Copy.objects.create(book=book, branch=self.branch, shelf='A-1')
        event_id = uuid.uuid4()
        operations.ingest(None, self.rfid.pk, event_id, 'rfid_exit', {'rfids': [str(item.rfid)]})
        self.assertTrue(m.Alert.objects.filter(kind='theft').exists())

    def test_mqtt_topic_format(self):
        from pathlib import Path
        import sys

        root = Path(__file__).resolve().parents[3]
        sys.path.insert(0, str(root / 'iot-simulator'))
        from lib.topics import command_topic, device_topic  # noqa: WPS433

        self.assertEqual(device_topic(1, 2, 'event'), 'library/1/device/2/event')
        self.assertEqual(command_topic(1, 2), 'library/1/device/2/command')
