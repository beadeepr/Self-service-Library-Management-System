from datetime import timedelta
from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from library.models import (Alert, Book, Branch, Consent, Copy, Device, DeviceCommand,
    DeviceEvent, Inventory, Transfer, User, Visit, WorkOrder)
from .common import audit, require, rules, owner_or_admin
from .circulation import notify
from library.events import emit


def queue_command(actor, device, value, reason):
    import hashlib
    import hmac
    item = DeviceCommand.objects.create(device=device, actor=actor, command=value, reason=reason,
        status='simulated' if settings.SIMULATION_ENABLED else 'pending')
    stamp = int(item.created_at.timestamp())
    signed_content = f'{item.pk}|{device.pk}|{value}|{stamp}|{reason}'
    item.signature = hmac.new(settings.DEVICE_SIGNING_KEY.encode(), signed_content.encode(), hashlib.sha256).hexdigest()
    item.save(update_fields=['signature'])
    emit('device.command', branch=device.branch_id, device=device.pk, command_id=item.pk, command=value,
         timestamp=stamp, reason=reason, signature=item.signature, simulation=settings.SIMULATION_ENABLED)
    return item


def raise_alert(branch, kind, message, severity='warning', device=None):
    alert = Alert.objects.create(branch=branch, device=device, kind=kind, message=message, severity=severity)
    for user in User.objects.filter(role__in=['admin', 'operator'], is_active=True):
        notify(user, f'设备/安全告警：{kind}', message)
    if device and kind in ['offline', 'fault', 'smoke']:
        WorkOrder.objects.create(branch=branch, device=device, kind='technical', title=message,
            due_at=timezone.now()+timedelta(hours=rules().response_hours))
    return alert


@transaction.atomic
def ingest(actor, device_id, event_id, kind, payload):
    device = get_object_or_404(Device.objects.select_for_update(), pk=device_id)
    existing = DeviceEvent.objects.filter(event_id=event_id).first()
    if existing:
        require(existing.device_id == device.pk and existing.kind == kind and existing.payload == payload, '事件 ID 已用于其他数据')
        return {'id': existing.pk, 'duplicate': True}
    event = DeviceEvent.objects.create(device=device, event_id=event_id, kind=kind, payload=payload)
    device.online = True
    device.last_seen = timezone.now()
    device.shadow = payload
    device.save()
    if kind in ['fault', 'smoke', 'help', 'security']:
        raise_alert(device.branch, kind, str(payload.get('message', kind)), 'critical' if kind in ['smoke', 'help'] else 'warning', device)
    if kind == 'smoke':
        for gate in Device.objects.filter(branch=device.branch, kind='gate'):
            item = queue_command(actor, gate, 'unlock', f'烟感联动事件 {event.pk}')
            audit(actor, 'emergency.fire_unlock', item)
    if kind == 'rfid_exit':
        tags = payload.get('rfids', [])
        require(isinstance(tags, list) and len(tags) <= 100, 'rfids 必须是最多 100 项的列表')
        import uuid
        try:
            tags = [uuid.UUID(str(tag)) for tag in tags]
        except ValueError:
            require(False, 'RFID 格式错误')
        unsafe = list(Copy.objects.filter(rfid__in=tags).exclude(status='loaned').values_list('id', flat=True))
        if unsafe:
            raise_alert(device.branch, 'theft', f'未借出图书离馆：{unsafe}', 'critical', device)
    if kind == 'inventory':
        import uuid
        tags, shelf = payload.get('observed'), payload.get('shelf', '')
        require(isinstance(tags, list) and len(tags) <= 10000, '盘点事件须包含最多 10000 项的 observed 列表')
        require(isinstance(shelf, str) and len(shelf) <= 100, '书架编号格式错误')
        try:
            tags = [uuid.UUID(str(tag)) for tag in tags]
        except ValueError:
            require(False, '盘点 RFID 格式错误')
        inventory(actor, device.branch_id, shelf, tags)
    audit(actor, 'device.event', event)
    return {'id': event.pk, 'duplicate': False}


@transaction.atomic
def command(actor, device_id, value, reason):
    device = get_object_or_404(Device.objects.select_for_update(), pk=device_id)
    require(value in ['power_on', 'power_off', 'restart', 'unlock', 'broadcast'], '不支持此设备命令')
    require(value != 'unlock' or device.kind == 'gate', '仅门禁设备支持解锁')
    item = queue_command(actor, device, value, reason)
    audit(actor, 'device.command', item, command=value, reason=reason)
    return {'id': item.pk, 'status': item.status}


@transaction.atomic
def access(actor, reader_id, branch_id, direction, method):
    owner_or_admin(actor, reader_id)
    reader = get_object_or_404(User.objects.select_for_update(), pk=reader_id)
    branch = get_object_or_404(Branch.objects.select_for_update(), pk=branch_id)
    visit = Visit.objects.select_for_update().filter(reader=reader, exited_at=None).first()
    if direction == 'exit':
        require(visit and visit.branch_id == branch.pk, '没有对应的在馆记录')
        visit.exited_at = timezone.now()
        visit.active_reader = None
        visit.save()
    else:
        require(branch.active, '网点暂未开放')
        require(reader.is_active and not reader.frozen and reader.credit >= rules().minimum_credit, '账号状态或信用不满足入馆条件')
        require(not visit, '请勿重复入馆')
        if method == 'face':
            consent = Consent.objects.filter(reader=reader, purpose='biometric').order_by('-id').first()
            require(consent and consent.granted, '未取得生物识别单独同意')
            require(settings.SIMULATION_ENABLED, '人脸识别供应商尚未配置')
        current = timezone.localtime().time()
        start, end = branch.opening_time, branch.closing_time
        opened = start == end or (start <= current < end if start < end else current >= start or current < end)
        require(opened, '当前不在开放时间内')
        require(Visit.objects.filter(branch=branch, exited_at=None).count() < branch.capacity, '当前在馆人数已达上限')
        visit = Visit.objects.create(reader=reader, active_reader=reader, branch=branch, entered_at=timezone.now())
    audit(actor, f'access.{direction}', visit, method=method)
    return {'id': visit.pk, 'direction': direction, 'occupancy': Visit.objects.filter(branch=branch, exited_at=None).count()}


@transaction.atomic
def plan_transfer(actor, copy_id, destination_id, route, schedule):
    copy = get_object_or_404(Copy.objects.select_for_update(), pk=copy_id)
    destination = get_object_or_404(Branch, pk=destination_id, active=True)
    require(copy.status == 'available', '仅在馆可借图书可调拨')
    require(copy.branch_id != destination_id, '目标馆不能与来源馆相同')
    require(not Transfer.objects.filter(copy=copy, status__in=['planned', 'shipped']).exists(), '已有未完成配送任务')
    transfer = Transfer.objects.create(copy=copy, source=copy.branch, destination=destination, route=route, schedule=schedule)
    copy.status = 'withdrawn'
    copy.save()
    audit(actor, 'transfer.plan', transfer)
    return {'id': transfer.pk, 'status': transfer.status}


@transaction.atomic
def transition_transfer(actor, pk, action, destination_id=None):
    snapshot = get_object_or_404(Transfer, pk=pk)
    copy = Copy.objects.select_for_update().get(pk=snapshot.copy_id)
    item = Transfer.objects.select_for_update().get(pk=pk)
    if action == 'ship':
        require(item.status == 'planned', '仅待发货任务可发货')
        item.status, copy.status = 'shipped', 'transit'
    elif action == 'receive':
        require(item.status == 'shipped', '仅在途任务可验收')
        item.status, copy.status = 'received', 'processing'
        copy.branch = item.destination
        copy.disinfected_at = None
        copy.shelving_due_at = timezone.now()+timedelta(hours=rules().shelving_hours)
    elif action == 'cancel':
        require(item.status == 'planned', '在途任务请先退回验收')
        item.status, copy.status = 'cancelled', 'available'
    elif action in ['redirect', 'return']:
        require(item.status in ['planned', 'shipped'], '已完成任务不可改派')
        item.destination = item.source if action == 'return' else get_object_or_404(Branch, pk=destination_id, active=True)
    item.save()
    copy.save()
    audit(actor, f'transfer.{action}', item)
    return {'id': item.pk, 'status': item.status}


@transaction.atomic
def inventory(actor, branch_id, shelf, observed):
    branch = get_object_or_404(Branch, pk=branch_id)
    expected = Copy.objects.filter(branch=branch, status__in=['available', 'reserved'])
    if shelf:
        expected = expected.filter(shelf=shelf)
    expected_tags = {str(tag) for tag in expected.values_list('rfid', flat=True)}
    seen = {str(tag) for tag in observed}
    known = Copy.objects.filter(rfid__in=seen)
    misplaced = [str(item.rfid) for item in known if item.branch_id != branch_id or (shelf and item.shelf != shelf)]
    result = Inventory.objects.create(branch=branch, shelf=shelf, observed=sorted(seen), report={
        'missing': sorted(expected_tags-seen), 'surplus': sorted(seen-expected_tags), 'misplaced': misplaced})
    audit(actor, 'inventory.scan', result)
    return {'id': result.pk, 'report': result.report}
