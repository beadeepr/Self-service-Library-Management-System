from decimal import Decimal
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import permissions, viewsets, mixins
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied
from library import models as m
from library.services import authentication, circulation
from library.services.common import audit, idempotent, is_admin, require, rules
from . import serializers as s
from .auth import validated
from .common import AdminOnly, StaffOnly, PublicReadAdminWrite


class AuditedModelViewSet(viewsets.ModelViewSet):
    permission_classes = [AdminOnly]

    def perform_create(self, serializer):
        with transaction.atomic():
            obj = serializer.save()
            audit(self.request.user, 'resource.create', obj)

    def perform_update(self, serializer):
        with transaction.atomic():
            obj = serializer.save()
            audit(self.request.user, 'resource.update', obj)

    def perform_destroy(self, instance):
        with transaction.atomic():
            audit(self.request.user, 'resource.delete', instance)
            instance.delete()


class BranchViewSet(AuditedModelViewSet):
    queryset = m.Branch.objects.all()
    serializer_class = s.BranchSerializer
    permission_classes = [PublicReadAdminWrite]

    @action(detail=True, methods=['get'])
    def occupancy(self, request, pk=None):
        branch = self.get_object()
        count = m.Visit.objects.filter(branch=branch, exited_at=None).count()
        return Response({'branch': branch.pk, 'occupancy': count, 'capacity': branch.capacity,
                         'seats': branch.seats, 'estimated_free_seats': max(0, branch.seats-count)})


class CategoryViewSet(AuditedModelViewSet):
    queryset = m.Category.objects.all()
    serializer_class = s.CategorySerializer
    permission_classes = [PublicReadAdminWrite]


class BookViewSet(AuditedModelViewSet):
    queryset = m.Book.objects.select_related('category').annotate(
        total_count=Count('copies'), available_count=Count('copies', filter=Q(copies__status='available')),
        loaned_count=Count('copies', filter=Q(copies__status='loaned'))).order_by('-id')
    serializer_class = s.BookSerializer
    permission_classes = [PublicReadAdminWrite]
    search_fields = ['title', 'isbn', 'author', 'category__code', 'call_number']
    filterset_fields = ['isbn', 'category', 'author', 'active']
    ordering_fields = ['id', 'title', 'price']

    @extend_schema(request=s.IntakeSerializer)
    @action(detail=True, methods=['post'], permission_classes=[AdminOnly])
    def intake(self, request, pk=None):
        book = self.get_object()
        data = validated(s.IntakeSerializer, request)
        def execute():
            copies = [m.Copy.objects.create(book=book, branch=data['branch'], shelf=data['shelf']) for _ in range(data['quantity'])]
            audit(request.user, 'book.intake', book, quantity=len(copies))
            return {'copies': s.CopySerializer(copies, many=True).data}
        return Response(idempotent(request.user, request.headers.get('Idempotency-Key'), f'book.intake:{pk}', request.data, execute), status=201)


class CopyViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = m.Copy.objects.select_related('book', 'branch').all()
    serializer_class = s.CopySerializer
    permission_classes = [PublicReadAdminWrite]
    filterset_fields = ['book', 'branch', 'status', 'rfid', 'shelf']

    @action(detail=True, methods=['post'], permission_classes=[StaffOnly])
    def disinfect(self, request, pk=None):
        with transaction.atomic():
            copy = get_object_or_404(m.Copy.objects.select_for_update(), pk=pk)
            require(copy.status == 'processing', '仅待处理图书可登记消毒')
            copy.disinfected_at = timezone.now()
            copy.save()
            audit(request.user, 'copy.disinfect', copy)
        return Response(self.get_serializer(copy).data)

    @extend_schema(request=s.ShelfSerializer)
    @action(detail=True, methods=['post'], permission_classes=[StaffOnly])
    def shelve(self, request, pk=None):
        data = validated(s.ShelfSerializer, request)
        return Response(circulation.shelve(request.user, pk, data['shelf']))

    @extend_schema(request=s.CopyStatusSerializer)
    @action(detail=True, methods=['post'], permission_classes=[AdminOnly], url_path='set-status')
    def set_status(self, request, pk=None):
        data = validated(s.CopyStatusSerializer, request)
        with transaction.atomic():
            copy = get_object_or_404(m.Copy.objects.select_for_update(), pk=pk)
            require(copy.status not in ['loaned', 'reserved', 'transit'], '须先结束借阅、预约或配送流程')
            require(not m.Transfer.objects.filter(copy=copy, status='planned').exists(), '图书已有待发货任务')
            copy.status = data['status']
            copy.save()
            audit(request.user, 'copy.status', copy, **data)
        return Response(self.get_serializer(copy).data)


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


class RuleViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet):
    queryset = m.Rule.objects.all()
    serializer_class = s.RuleSerializer
    permission_classes = [AdminOnly]

    def get_queryset(self):
        rules()
        return super().get_queryset()

    def perform_update(self, serializer):
        with transaction.atomic():
            obj = serializer.save()
            audit(self.request.user, 'rules.update', obj)


class AnnouncementViewSet(AuditedModelViewSet):
    queryset = m.Announcement.objects.all()
    serializer_class = s.AnnouncementSerializer
    permission_classes = [PublicReadAdminWrite]

    def get_queryset(self):
        return self.queryset if is_admin(self.request.user) else self.queryset.filter(published=True)


class ConsentViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet):
    queryset = m.Consent.objects.all()
    serializer_class = s.ConsentSerializer

    def get_queryset(self):
        return self.queryset.filter(reader=self.request.user)

    def perform_create(self, serializer):
        with transaction.atomic():
            obj = serializer.save(reader=self.request.user)
            audit(self.request.user, 'privacy.consent', obj)


class OperationRecordViewSet(AuditedModelViewSet):
    queryset = m.OperationRecord.objects.all()
    serializer_class = s.OperationRecordSerializer
    permission_classes = [StaffOnly]
    filterset_fields = ['branch', 'kind', 'occurred_on']

    def retrieve(self, request, *args, **kwargs):
        obj = self.get_object()
        audit(request.user, 'operation.read', obj)
        return Response(self.get_serializer(obj).data)

    def list(self, request, *args, **kwargs):
        audit(request.user, 'operation.list', request.user)
        return super().list(request, *args, **kwargs)


class ActivityViewSet(AuditedModelViewSet):
    queryset = m.Activity.objects.all()
    serializer_class = s.ActivitySerializer
    permission_classes = [PublicReadAdminWrite]

    def get_queryset(self):
        return self.queryset if is_admin(self.request.user) else self.queryset.filter(published=True)

    @action(detail=True, methods=['post', 'delete'], permission_classes=[permissions.IsAuthenticated])
    def enroll(self, request, pk=None):
        with transaction.atomic():
            activity = get_object_or_404(m.Activity.objects.select_for_update(), pk=pk, published=True)
            require(activity.starts_at > timezone.now(), '活动已开始')
            existing = m.Enrollment.objects.filter(activity=activity, reader=request.user)
            if request.method == 'DELETE':
                existing.delete()
                return Response(status=204)
            if not existing.exists():
                require(activity.enrollments.count() < activity.capacity, '活动报名已满')
                m.Enrollment.objects.create(activity=activity, reader=request.user)
            audit(request.user, 'activity.enroll', activity)
            return Response({'enrolled': True})
