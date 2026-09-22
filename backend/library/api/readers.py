from rest_framework import mixins
from rest_framework.exceptions import PermissionDenied
from library.services import auth_service as authentication, reader_service as circulation
from django.db import transaction
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from library import models as m
from library.services.common import audit, idempotent, require
from . import serializers as s
from .auth import validated
from .common import AdminOnly
from .base import OwnedReadViewSet


class ReaderViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = m.User.objects.all().order_by('-id')
    serializer_class = s.UserSerializer
    permission_classes = [AdminOnly]
    search_fields = ['username']
    filterset_fields = ['role', 'frozen', 'verified', 'phone', 'first_name']

    @action(detail=False, methods=['get', 'patch'], permission_classes=[permissions.IsAuthenticated])
    def me(self, request):
        reader = request.user
        if request.method == 'PATCH':
            with transaction.atomic():
                reader = get_object_or_404(m.User.objects.select_for_update(), pk=request.user.pk)
                if not reader.is_active or reader.frozen:
                    raise PermissionDenied('账户已冻结或停用，无法修改资料')
                serializer = self.get_serializer(reader, data=request.data, partial=True)
                serializer.is_valid(raise_exception=True)
                serializer.save()
                audit(request.user, 'reader.profile', reader)
        return Response(self.get_serializer(reader).data)

    @extend_schema(request=s.PasswordSerializer)
    @action(detail=False, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def password(self, request):
        data = validated(s.PasswordSerializer, request)
        require(request.user.check_password(data['old_password']), '原密码错误')
        authentication.validate_secret(data['new_password'], request.user)
        request.user.set_password(data['new_password'])
        request.user.save(update_fields=['password'])
        audit(request.user, 'reader.password', request.user)
        return Response({'detail': '密码已修改，请重新登录'})

    @extend_schema(request=s.SmsLoginSerializer)
    @action(detail=False, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def phone(self, request):
        data = validated(s.SmsLoginSerializer, request)
        authentication.consume_code(data['phone'], 'phone', data['code'])
        require(not m.User.objects.filter(phone=data['phone']).exclude(pk=request.user.pk).exists(), '手机号已被使用')
        request.user.phone = data['phone']
        request.user.save(update_fields=['phone'])
        audit(request.user, 'reader.phone', request.user)
        return Response(self.get_serializer(request.user).data)

    @extend_schema(request=s.IdentitySerializer)
    @action(detail=False, methods=['post'], permission_classes=[permissions.IsAuthenticated], url_path='verify-identity')
    def verify_identity(self, request):
        data = validated(s.IdentitySerializer, request)
        return Response(authentication.verify_identity(request.user, data['identity']))

    @extend_schema(request=s.ReaderAdminSerializer)
    @action(detail=True, methods=['post'])
    def manage(self, request, pk=None):
        data = validated(s.ReaderAdminSerializer, request)
        def execute():
            user = get_object_or_404(m.User.objects.select_for_update(), pk=pk)
            require(not user.is_superuser or request.user.is_superuser, '只有超级管理员可修改超级管理员')
            if 'role' in data:
                require(request.user.is_superuser, '只有超级管理员可授予或调整角色')
                user.role = data['role']
            if 'frozen' in data:
                user.frozen = data['frozen']
            if 'deposit_delta' in data:
                require(user.deposit+data['deposit_delta'] >= 0, '押金余额不足')
                user.deposit += data['deposit_delta']
                m.DepositEntry.objects.create(reader=user, delta=data['deposit_delta'], balance=user.deposit, reason=data['reason'])
            if 'new_password' in data:
                authentication.validate_secret(data['new_password'], user)
                user.set_password(data['new_password'])
            user.save()
            if 'credit_delta' in data:
                circulation.change_credit(user, data['credit_delta'], data['reason'])
            audit(request.user, 'reader.manage', user, reason=data['reason'], fields=[key for key in data if key != 'new_password'])
            return {'id': user.pk, 'role': user.role, 'credit': user.credit, 'deposit': str(user.deposit), 'frozen': user.frozen}
        return Response(idempotent(request.user, request.headers.get('Idempotency-Key'), f'reader.manage:{pk}', request.data, execute))



class ConsentViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet):
    queryset = m.Consent.objects.all()
    serializer_class = s.ConsentSerializer

    def get_queryset(self):
        return self.queryset.filter(reader=self.request.user)

    def perform_create(self, serializer):
        with transaction.atomic():
            obj = serializer.save(reader=self.request.user)
            audit(self.request.user, 'privacy.consent', obj)



class CreditViewSet(OwnedReadViewSet):
    queryset = m.CreditEntry.objects.all()
    serializer_class = s.CreditEntrySerializer



class DepositViewSet(OwnedReadViewSet):
    queryset = m.DepositEntry.objects.all()
    serializer_class = s.DepositEntrySerializer
