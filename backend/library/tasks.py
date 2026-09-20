from datetime import timedelta
from celery import shared_task
from django.db import transaction
from django.utils import timezone
from library.models import (Book, Copy, Device, Loan, Reservation, User, Visit,
    DeviceEvent, Notification, OperationRecord, VerificationCode, LoginChallenge,
    Fine, Payment, CreditEntry, DepositEntry, AuditLog, Idempotency)
from library.services.common import rules
from library.services.circulation import assess_fine, assign_hold, notify
from library.services.operations import raise_alert


@shared_task
def maintenance():
    now = timezone.now()
    for pk in Reservation.objects.filter(status='ready', expires_at__lte=now).values_list('pk', flat=True):
        with transaction.atomic():
            snapshot = Reservation.objects.get(pk=pk)
            Book.objects.select_for_update().get(pk=snapshot.book_id)
            hold = Reservation.objects.select_for_update().get(pk=pk)
            if hold.status == 'ready' and hold.expires_at <= now:
                hold.status = 'expired'
                hold.save()
                assign_hold(Copy.objects.select_for_update().get(pk=hold.copy_id))
    for pk in Loan.objects.filter(returned_at=None, due_at__lt=now+timedelta(days=2)).values_list('pk', flat=True):
        with transaction.atomic():
            snapshot = Loan.objects.get(pk=pk)
            User.objects.select_for_update().get(pk=snapshot.reader_id)
            loan = Loan.objects.select_for_update().get(pk=pk)
            if loan.returned_at is not None:
                continue
            overdue = loan.due_at < now
            if overdue:
                assess_fine(loan)
            notify(loan.reader, '图书逾期' if overdue else '图书即将到期', f'借阅 {pk} 应于 {loan.due_at.isoformat()} 归还',
                f'loan:{pk}:{"overdue" if overdue else "due"}:{now.date()}')
    cutoff = now-timedelta(minutes=rules().offline_minutes)
    for pk in Device.objects.filter(online=True, last_seen__lt=cutoff).values_list('pk', flat=True):
        with transaction.atomic():
            device = Device.objects.select_for_update().get(pk=pk)
            if device.online and device.last_seen < cutoff:
                device.online = False
                device.save()
                raise_alert(device.branch, 'offline', f'设备 {device.name} 离线', device=device)
    return {'status': 'ok'}


@shared_task
def purge_expired():
    now = timezone.now()
    cutoff = now-timedelta(days=rules().retention_days)
    counts = {}
    for model in [DeviceEvent, Notification]:
        counts[model.__name__] = model.objects.filter(created_at__lt=cutoff).delete()[0]
    counts['visits'] = Visit.objects.filter(exited_at__lt=cutoff).delete()[0]
    counts['videos'] = OperationRecord.objects.filter(kind='video', expires_at__lte=now).delete()[0]
    VerificationCode.objects.filter(expires_at__lt=now).delete()
    LoginChallenge.objects.filter(expires_at__lt=now).delete()
    CreditEntry.objects.filter(created_at__lt=cutoff).delete()
    # Unsettled balances and active circulation are never deleted by retention jobs.
    financial_cutoff = now-timedelta(days=rules().financial_retention_days)
    with transaction.atomic():
        old_loans = Loan.objects.select_for_update().filter(returned_at__lt=cutoff)
        for loan in old_loans:
            fine = Fine.objects.filter(loan=loan).first()
            if fine:
                if fine.paid_amount < fine.amount or fine.updated_at >= financial_cutoff:
                    continue
                if Payment.objects.filter(fine=fine, updated_at__gte=financial_cutoff).exists():
                    continue
                Payment.objects.filter(fine=fine).delete()
                fine.delete()
            loan.delete()
        AuditLog.objects.filter(created_at__lt=financial_cutoff).delete()
        DepositEntry.objects.filter(created_at__lt=financial_cutoff).delete()
        Idempotency.objects.filter(created_at__lt=financial_cutoff).delete()
    return counts


@shared_task
def publish_events():
    import json
    from library.adapters import mqtt_client, connect
    from library.models import DomainEvent
    pending = list(DomainEvent.objects.filter(published_at=None).order_by('id')[:100])
    if not pending:
        return 0
    client = mqtt_client('library-outbox-publisher')
    connect(client)
    client.loop_start()
    try:
        for event in pending:
            payload = {'event_id': str(event.event_id), 'kind': event.kind, 'payload': event.payload}
            topic = f'library/{event.payload.get("branch", 0)}/domain/event'
            if event.kind == 'device.command':
                topic = f'library/{event.payload["branch"]}/device/{event.payload["device"]}/command'
            message = client.publish(topic, json.dumps(payload), qos=1)
            message.wait_for_publish(timeout=5)
            if not message.is_published():
                raise RuntimeError('MQTT 发布未确认，保留事件供下次重试')
            DomainEvent.objects.filter(pk=event.pk, published_at=None).update(published_at=timezone.now())
    finally:
        client.disconnect()
        client.loop_stop()
    return len(pending)
