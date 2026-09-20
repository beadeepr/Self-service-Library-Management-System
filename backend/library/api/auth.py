import hashlib
import secrets
import uuid
from datetime import timedelta
from django.core.cache import cache
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from library.models import LoginChallenge, User
from library.services import authentication as service
from library.services.common import audit, require
from . import serializers as s


def validated(serializer_class, request):
    serializer = serializer_class(data=request.data)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data


class AuthViewSet(viewsets.GenericViewSet):
    serializer_class = s.EmptySerializer
    permission_classes = [permissions.AllowAny]

    @action(detail=False, methods=['get'])
    def captcha(self, request):
        code = ''.join(secrets.choice('23456789ABCDEFGHJKLMNPQRSTUVWXYZ') for _ in range(5))
        token = str(uuid.uuid4())
        cache.set(f'captcha:{token}', hashlib.sha256(code.encode()).hexdigest(), 300)
        # SVG image can be rendered directly by the browser, no raster dependency.
        svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="160" height="50"><rect width="160" height="50" fill="#edf2f7"/><path d="M0 12L160 40M0 40L160 10" stroke="#a0aec0"/><text x="15" y="35" font-size="28" letter-spacing="5">{code}</text></svg>'
        import base64
        return Response({'captcha_id': token, 'image': 'data:image/svg+xml;base64,'+base64.b64encode(svg.encode()).decode(), 'expires_in': 300})

    @extend_schema(request=s.CodeRequestSerializer)
    @action(detail=False, methods=['post'], url_path='sms-code')
    def sms_code(self, request):
        data = validated(s.CodeRequestSerializer, request)
        key = f'captcha:{data["captcha_id"]}'
        digest = cache.get(key)
        cache.delete(key)
        require(digest and secrets.compare_digest(digest, hashlib.sha256(data['captcha_answer'].upper().encode()).hexdigest()), '图形验证码错误或已过期')
        return Response(service.issue_code(data['phone'], data['purpose']))

    @extend_schema(request=s.RegisterSerializer, responses=s.UserSerializer)
    @action(detail=False, methods=['post'])
    def register(self, request):
        data = validated(s.RegisterSerializer, request)
        service.consume_code(data['phone'], 'register', data['code'])
        require(not User.objects.filter(phone=data['phone']).exists(), '手机号已注册')
        user = User.objects.create_user(username='reader_'+uuid.uuid4().hex, phone=data['phone'], password=data['password'], first_name=data['first_name'])
        audit(user, 'auth.register', user)
        return Response(s.UserSerializer(user).data, status=201)

    @extend_schema(request=s.LoginSerializer)
    @action(detail=False, methods=['post'])
    def login(self, request):
        data = validated(s.LoginSerializer, request)
        return Response(service.password_login(data['phone'], data['password']))

    @extend_schema(request=s.SmsLoginSerializer)
    @action(detail=False, methods=['post'], url_path='sms-login')
    def sms_login(self, request):
        data = validated(s.SmsLoginSerializer, request)
        service.consume_code(data['phone'], 'login', data['code'])
        user = get_object_or_404(User, phone=data['phone'])
        return Response(service.tokens(user))

    @action(detail=False, methods=['post'], url_path='qr-challenge')
    def qr_challenge(self, request):
        secret = secrets.token_urlsafe(32)
        item = LoginChallenge.objects.create(poll_digest=hashlib.sha256(secret.encode()).hexdigest(), expires_at=timezone.now()+timedelta(minutes=5))
        return Response({'token': item.token, 'poll_secret': secret, 'expires_in': 300})

    @extend_schema(request=s.QrConfirmSerializer)
    @action(detail=False, methods=['post'], url_path='qr-confirm', permission_classes=[permissions.IsAuthenticated])
    def qr_confirm(self, request):
        data = validated(s.QrConfirmSerializer, request)
        with transaction.atomic():
            item = get_object_or_404(LoginChallenge.objects.select_for_update(), token=data['token'])
            require(not item.consumed and item.reader_id is None and item.expires_at > timezone.now(), '二维码已过期或已确认')
            item.reader = request.user
            item.save()
        return Response({'confirmed': True})

    @extend_schema(request=s.QrPollSerializer)
    @action(detail=False, methods=['post'], url_path='qr-poll')
    def qr_poll(self, request):
        data = validated(s.QrPollSerializer, request)
        with transaction.atomic():
            item = get_object_or_404(LoginChallenge.objects.select_for_update(), token=data['token'])
            require(secrets.compare_digest(item.poll_digest, hashlib.sha256(data['poll_secret'].encode()).hexdigest()), '轮询凭证错误')
            require(not item.consumed and item.expires_at > timezone.now(), '二维码已过期或已使用')
            if not item.reader_id:
                return Response({'status': 'waiting'})
            result = service.tokens(item.reader)
            item.consumed = True
            item.save()
        return Response(result)
