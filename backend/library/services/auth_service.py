import secrets
from datetime import timedelta
from django.conf import settings
from django.contrib.auth.hashers import make_password, check_password
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError, AuthenticationFailed
from rest_framework_simplejwt.tokens import RefreshToken
from library.models import User, VerificationCode
from .common import require, audit
from .reader_service import verify_identity


def validate_secret(password, user=None):
    try:
        validate_password(password, user)
    except DjangoValidationError as error:
        raise ValidationError({'password': error.messages})


def tokens(user):
    require(user.is_active and not user.frozen, '账号已冻结或停用')
    refresh = RefreshToken.for_user(user)
    return {'access': str(refresh.access_token), 'refresh': str(refresh), 'role': user.role}


def issue_code(phone, purpose):
    require(settings.SIMULATION_ENABLED, '短信供应商尚未配置')
    require(not VerificationCode.objects.filter(phone=phone, created_at__gt=timezone.now()-timedelta(seconds=60)).exists(), '请在 60 秒后重试')
    code = f'{secrets.randbelow(1000000):06d}'
    VerificationCode.objects.create(phone=phone, purpose=purpose, digest=make_password(code), expires_at=timezone.now()+timedelta(minutes=5))
    return {'expires_in': 300, 'simulation': True, 'simulation_code': code}


def consume_code(phone, purpose, code):
    # Commit failed attempts before raising: errors must not roll back lockouts.
    valid = False
    with transaction.atomic():
        row = VerificationCode.objects.select_for_update().filter(phone=phone, purpose=purpose).order_by('-id').first()
        if row and not row.consumed and row.expires_at > timezone.now() and row.attempts < 5:
            row.attempts += 1
            valid = check_password(code, row.digest)
            row.consumed = valid
            row.save()
    require(valid, '验证码错误、过期或已锁定，请重新获取')


def password_login(phone, password):
    user = None
    with transaction.atomic():
        user = User.objects.select_for_update().filter(phone=phone).first()
        if user is None:
            make_password(password)
        elif not user.locked_until or user.locked_until <= timezone.now():
            if user.locked_until:
                user.failed_logins = 0
                user.locked_until = None
            if user.check_password(password):
                user.failed_logins = 0
                user.save(update_fields=['failed_logins', 'locked_until'])
                result = tokens(user)
                audit(user, 'auth.login', user)
                return result
            user.failed_logins += 1
            if user.failed_logins >= 5:
                user.locked_until = timezone.now() + timedelta(minutes=15)
            user.save(update_fields=['failed_logins', 'locked_until'])
    raise AuthenticationFailed('手机号或密码错误，连续 5 次错误后锁定 15 分钟')
