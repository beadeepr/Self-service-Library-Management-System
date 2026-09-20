import hashlib
import json
from django.utils.crypto import salted_hmac
from django.db import transaction
from rest_framework.exceptions import ValidationError, PermissionDenied, APIException
from library.models import AuditLog, Idempotency, Rule, User


def rules():
    return Rule.objects.get_or_create(name='default')[0]


def require(condition, message):
    if not condition:
        raise ValidationError({'detail': message})


class StockUnavailable(APIException):
    status_code = 200
    business_code = 4001
    default_detail = '图书不可借，请检查 RFID 或联系管理员'


def is_admin(user):
    return user.is_authenticated and (user.is_superuser or user.role == 'admin')


def is_staff(user):
    return is_admin(user) or (user.is_authenticated and user.role == 'operator')


def owner_or_admin(actor, reader_id):
    if actor.pk != reader_id and not is_admin(actor):
        raise PermissionDenied('只能操作自己的记录')


def audit(actor, action, obj, **details):
    return AuditLog.objects.create(actor=actor, action=action,
        resource=f'{obj.__class__.__name__}:{obj.pk}', details=details)


@transaction.atomic
def idempotent(actor, key, operation, payload, callback):
    require(isinstance(key, str) and 1 <= len(key) <= 128, '请提供 Idempotency-Key 请求头（1~128 字符）')
    # Serializes retries per actor, including creation of the idempotency record.
    User.objects.select_for_update().get(pk=actor.pk)
    digest = salted_hmac('idempotency', json.dumps(payload, sort_keys=True, default=str), algorithm='sha256').hexdigest()
    existing = Idempotency.objects.filter(actor=actor, key=key).first()
    if existing:
        require(existing.operation == operation and existing.digest == digest, '幂等键已用于不同请求')
        return existing.response
    result = callback()
    Idempotency.objects.create(actor=actor, key=key, operation=operation, digest=digest, response=result)
    return result
