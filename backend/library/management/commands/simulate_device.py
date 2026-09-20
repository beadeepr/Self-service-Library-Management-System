import json
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from library.adapters import mqtt_client, connect, event_envelope


class Command(BaseCommand):
    help = '向 MQTT 发布单次设备事件，例如 --device 1 --kind smoke --payload "{}"'

    def add_arguments(self, parser):
        parser.add_argument('--device', type=int, required=True)
        parser.add_argument('--kind', default='heartbeat')
        parser.add_argument('--payload', default='{}')

    def handle(self, *args, **options):
        if not settings.SIMULATION_ENABLED:
            raise CommandError('模拟设备已禁用')
        from library.api.serializers import DeviceEventInputSerializer
        event = event_envelope(options['kind'], json.loads(options['payload']))
        serializer = DeviceEventInputSerializer(data=event)
        serializer.is_valid(raise_exception=True)
        client = mqtt_client('library-simulator')
        connect(client)
        client.loop_start()
        try:
            from library.models import Device
            device = Device.objects.get(pk=options['device'])
            result = client.publish(f'library/{device.branch_id}/device/{device.pk}/event', json.dumps(event), qos=1)
            result.wait_for_publish(timeout=10)
            if not result.is_published():
                raise CommandError('MQTT 发布超时')
            self.stdout.write(json.dumps(event))
        finally:
            client.disconnect()
            client.loop_stop()
