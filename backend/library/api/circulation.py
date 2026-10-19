from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from library import models as m
from library.services import circulation_service as service, fine_service as payments
from library.services.common import audit, idempotent, is_admin, owner_or_admin, require
from . import serializers as s
from .auth import validated
from .common import AdminOnly



from .base import OwnedReadViewSet

class LoanViewSet(OwnedReadViewSet):
    queryset = m.Loan.objects.select_related('copy', 'reader').all()
    serializer_class = s.LoanSerializer
    filterset_fields = {'reader': ['exact'], 'copy': ['exact'], 'returned_at': ['isnull'], 'due_at': ['lt', 'gte']}

    @extend_schema(request=s.CirculationReturnSerializer)
    def return_by_id(self, request):
        data = validated(s.CirculationReturnSerializer, request)
        # 兼容旧接口保持原有的归属限制；自助终端使用 /loans/{id}/return/。
        loan = get_object_or_404(self.get_queryset(), pk=data['loan'])
        payload = {key: value for key, value in request.data.items() if key != 'loan'}
        return Response(idempotent(request.user, request.headers.get('Idempotency-Key'),
            f'loan.return:{loan.pk}', payload,
            lambda: service.return_book(request.user, loan.pk, data['branch'], data['damaged'])))

    @extend_schema(request=s.CirculationRenewSerializer)
    def renew_by_id(self, request):
        data = validated(s.CirculationRenewSerializer, request)
        loan = get_object_or_404(self.get_queryset(), pk=data['loan'])
        return Response(idempotent(request.user, request.headers.get('Idempotency-Key'),
            f'loan.renew:{loan.pk}', {}, lambda: service.renew(request.user, loan.pk)))

    @action(detail=False, methods=['get'], permission_classes=[permissions.IsAuthenticated])
    def lookup(self, request):
        """按副本查当前未归还的借阅，供自助还书使用（不限制借阅人）。"""
        copy_id = request.query_params.get('copy', '')
        require(str(copy_id).isdigit(), '请提供 copy 参数')
        loan = get_object_or_404(m.Loan.objects.select_related('copy'), copy_id=int(copy_id), returned_at=None)
        return Response({'id': loan.pk, 'copy': loan.copy_id, 'borrowed_at': loan.borrowed_at.isoformat(),
                         'due_at': loan.due_at.isoformat()})

    @extend_schema(request=s.BorrowSerializer)
    @action(detail=False, methods=['post'])
    def borrow(self, request):
        data = validated(s.BorrowSerializer, request)
        return Response(idempotent(request.user, request.headers.get('Idempotency-Key'), 'loan.borrow', request.data,
            lambda: service.borrow(request.user, data.get('reader', request.user.pk), data['copy'])), status=201)

    @extend_schema(request=s.ReturnSerializer)
    @action(detail=True, methods=['post'], url_path='return')
    def return_book(self, request, pk=None):
        # 自助还书允许替他人归还，因此不经过只返回本人借阅的 OwnedReadViewSet 过滤。
        loan = get_object_or_404(m.Loan, pk=pk)
        data = validated(s.ReturnSerializer, request)
        return Response(idempotent(request.user, request.headers.get('Idempotency-Key'), f'loan.return:{pk}', request.data,
            lambda: service.return_book(request.user, loan.pk, data['branch'], data['damaged'],
                allow_other_reader=True)))

    @extend_schema(request=s.EmptySerializer)
    @action(detail=True, methods=['post'])
    def renew(self, request, pk=None):
        loan = self.get_object()
        return Response(idempotent(request.user, request.headers.get('Idempotency-Key'), f'loan.renew:{pk}', {},
            lambda: service.renew(request.user, loan.pk)))

    @action(detail=True, methods=['post'], permission_classes=[AdminOnly])
    def remind(self, request, pk=None):
        loan = self.get_object()
        service.notify(loan.reader, '图书归还提醒', f'借阅 {loan.pk} 请于 {loan.due_at.isoformat()} 前归还')
        audit(request.user, 'loan.remind', loan)
        return Response({'sent': True, 'channel': 'inbox'})


from .readers import CreditViewSet, DepositViewSet
from .notifications import NotificationViewSet
from .reservations import ReservationViewSet
from .fines import FineViewSet, PaymentViewSet
