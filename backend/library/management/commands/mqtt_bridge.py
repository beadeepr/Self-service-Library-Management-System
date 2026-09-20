import logging
import time
from django.core.management.base import BaseCommand
from django.db import close_old_connections, DatabaseError
from library.adapters import mqtt_client, connect
from library.services.mqtt import record_message, process_message

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = '订阅 library/+/device/+/event，将 MQTT 仿真事件转入领域服务'

    def handle(self, *args, **options):
        client = mqtt_client('library-backend-bridge', persistent=True, manual_ack=True)

        def on_connect(client, userdata, flags, reason_code, properties):
            if reason_code.is_failure:
                logger.error('MQTT 连接失败：%s', reason_code)
            else:
                for suffix in ['event', 'telemetry', 'status']:
                    client.subscribe(f'library/+/device/+/{suffix}', qos=1)

        def on_message(client, userdata, message):
            close_old_connections()
            try:
                # record_message commits its transaction before ACK. A failed commit
                # propagates out of the callback and reconnects the persistent session.
                row = record_message(message.topic, message.payload)
                client.ack(message.mid, message.qos)
                try:
                    process_message(row.pk)
                except Exception:
                    logger.exception('MQTT 消息已持久化，等待后台重试：%s', row.pk)
            finally:
                close_old_connections()

        client.on_connect = on_connect
        client.on_message = on_message
        try:
            while True:
                try:
                    connect(client)
                    self.stdout.write('MQTT bridge started')
                    client.loop_forever()
                except (DatabaseError, OSError):
                    logger.exception('MQTT 连接或收件持久化失败，稍后重连；未落库消息不确认')
                finally:
                    client.disconnect()
                time.sleep(5)
        except KeyboardInterrupt:
            client.disconnect()
