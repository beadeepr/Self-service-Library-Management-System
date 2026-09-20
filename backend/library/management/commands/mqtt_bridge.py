import json
import logging
from django.core.management.base import BaseCommand
from django.db import close_old_connections
from library.adapters import mqtt_client, connect
from library.api.serializers import DeviceEventInputSerializer
from library.services.operations import ingest
from library.models import Device

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = '订阅 library/+/device/+/event，将 MQTT 仿真事件转入领域服务'

    def handle(self, *args, **options):
        client = mqtt_client('library-backend-bridge')

        def on_connect(client, userdata, flags, reason_code, properties):
            if reason_code.is_failure:
                logger.error('MQTT 连接失败：%s', reason_code)
            else:
                for suffix in ['event', 'telemetry', 'status']:
                    client.subscribe(f'library/+/device/+/{suffix}', qos=1)

        def on_message(client, userdata, message):
            close_old_connections()
            try:
                if len(message.payload) > 65536:
                    raise ValueError('MQTT 消息过大')
                parts = message.topic.split('/')
                branch_id, device_id, topic_kind = int(parts[1]), int(parts[3]), parts[4]
                if not Device.objects.filter(pk=device_id, branch_id=branch_id).exists():
                    raise ValueError('设备与 MQTT 网点主题不匹配')
                envelope = json.loads(message.payload)
                if topic_kind != 'event':
                    envelope['kind'] = 'telemetry' if topic_kind == 'telemetry' else 'heartbeat'
                serializer = DeviceEventInputSerializer(data=envelope)
                serializer.is_valid(raise_exception=True)
                data = serializer.validated_data
                ingest(None, device_id, data['event_id'], data['kind'], data['payload'])
            except Exception:
                logger.exception('MQTT 事件处理失败：%s', message.topic)
            finally:
                close_old_connections()

        client.on_connect = on_connect
        client.on_message = on_message
        connect(client)
        self.stdout.write('MQTT bridge started')
        try:
            client.loop_forever()
        except KeyboardInterrupt:
            client.disconnect()
