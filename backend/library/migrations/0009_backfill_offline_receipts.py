import uuid
from django.db import migrations


def backfill(apps, schema_editor):
    alias = schema_editor.connection.alias
    old = apps.get_model('library', 'Idempotency')
    receipts = apps.get_model('library', 'OfflineReceipt')
    for record in old.objects.using(alias).filter(operation='offline.sync', key__startswith='offline:').order_by('id').iterator():
        event_id = uuid.UUID(record.key[len('offline:'):])
        receipt, created = receipts.objects.using(alias).get_or_create(event_id=event_id, defaults={
            'uploaded_by_id': record.actor_id, 'digest': record.digest, 'response': record.response,
        })
        if not created and (receipt.digest != record.digest or receipt.response != record.response):
            raise RuntimeError(f'离线事件 {event_id} 存在冲突的历史处理结果，请先核对借阅记录和幂等记录再迁移')
        if created:
            receipts.objects.using(alias).filter(pk=receipt.pk).update(created_at=record.created_at, updated_at=record.updated_at)


class Migration(migrations.Migration):
    dependencies = [('library', '0008_mqttinbox_offlinereceipt')]
    operations = [migrations.RunPython(backfill, migrations.RunPython.noop, atomic=True)]
