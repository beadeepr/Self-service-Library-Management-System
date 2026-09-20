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

    @extend_schema(request=s.BorrowSerializer)
    @action(detail=False, methods=['post'])
    def borrow(self, request):
        data = validated(s.BorrowSerializer, request)
        return Response(idempotent(request.user, request.headers.get('Idempotency-Key'), 'loan.borrow', request.data,
            lambda: service.borrow(request.user, data.get('reader', request.user.pk), data['copy'])), status=201)

    @extend_schema(request=s.ReturnSerializer)
    @action(detail=True, methods=['post'], url_path='return')
    def return_book(self, request, pk=None):
        loan = self.get_object()
        data = validated(s.ReturnSerializer, request)
        return Response(idempotent(request.user, request.headers.get('Idempotency-Key'), f'loan.return:{pk}', request.data,
            lambda: service.return_book(request.user, loan.pk, data['branch'], data['damaged'])))

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
