import hashlib
import json
from django.db import transaction
from django.http import Http404
from rest_framework.exceptions import ValidationError
from library.api.serializers import DeviceEventInputSerializer
from library.models import Device, MqttInbox
from library.services.operations import ingest


@transaction.atomic
def record_message(topic, payload):
    payload = bytes(payload)
    digest = hashlib.sha256(topic.encode() + b'\0' + payload).hexdigest()
    oversized = len(payload) > 65536 or len(topic) > 512
    row, _ = MqttInbox.objects.get_or_create(digest=digest, defaults={
        'topic': topic[:512], 'payload': payload[:65536],
        'status': 'rejected' if oversized else 'pending',
        'error': 'MQTT 主题或消息超出长度限制' if oversized else '',
    })
    return row


@transaction.atomic
def process_message(pk):
    row = MqttInbox.objects.select_for_update().get(pk=pk)
    if row.status != 'pending':
        return row.status
    try:
        # Savepoint rolls back any partial domain write before rejecting invalid input.
        with transaction.atomic():
            parts = row.topic.split('/')
            if len(parts) != 5 or parts[0] != 'library' or parts[2] != 'device' or parts[4] not in ['event', 'telemetry', 'status']:
                raise ValueError('MQTT 主题格式错误')
            branch_id, device_id = int(parts[1]), int(parts[3])
            if not Device.objects.filter(pk=device_id, branch_id=branch_id).exists():
                raise ValueError('设备与 MQTT 网点主题不匹配')
            envelope = json.loads(bytes(row.payload))
            if not isinstance(envelope, dict):
                raise ValueError('MQTT 消息必须是 JSON 对象')
            if parts[4] != 'event':
                envelope['kind'] = 'telemetry' if parts[4] == 'telemetry' else 'heartbeat'
            serializer = DeviceEventInputSerializer(data=envelope)
            serializer.is_valid(raise_exception=True)
            data = serializer.validated_data
            ingest(None, device_id, data['event_id'], data['kind'], data['payload'])
    except (ValueError, UnicodeError, ValidationError, Http404) as exc:
        row.status = 'rejected'
        row.error = str(exc)[:2000]
    else:
        row.status = 'processed'
        row.error = ''
    row.save(update_fields=['status', 'error', 'updated_at'])
    return row.status
