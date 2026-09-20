from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from library import models as m
from library.services import circulation as service, payments
from library.services.common import audit, idempotent, is_admin, owner_or_admin, require
from . import serializers as s
from .auth import validated
from .common import AdminOnly


class OwnedReadViewSet(viewsets.ReadOnlyModelViewSet):
    owner_field = 'reader'

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return self.queryset.none()
        if is_admin(self.request.user):
            return self.queryset
        return self.queryset.filter(**{self.owner_field: self.request.user})

    def retrieve(self, request, *args, **kwargs):
        item = self.get_object()
        audit(request.user, 'record.read', item)
        return Response(self.get_serializer(item).data)

    def list(self, request, *args, **kwargs):
        audit(request.user, 'record.list', request.user, resource_type=self.queryset.model.__name__)
        return super().list(request, *args, **kwargs)


class LoanViewSet(OwnedReadViewSet):
    queryset = m.Loan.objects.select_related('copy', 'reader').all()
    serializer_class = s.LoanSerializer
    filterset_fields = {'reader': ['exact'], 'copy': ['exact'], 'returned_at': ['isnull'], 'due_at': ['lt', 'gte']}

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


class ReservationViewSet(OwnedReadViewSet):
    queryset = m.Reservation.objects.all()
    serializer_class = s.ReservationSerializer
    filterset_fields = ['status', 'book', 'branch']

    @extend_schema(request=s.ReserveSerializer)
    def create(self, request):
        data = validated(s.ReserveSerializer, request)
        return Response(idempotent(request.user, request.headers.get('Idempotency-Key'), 'reservation.create', request.data,
            lambda: service.reserve(request.user, data['book'], data['branch'])), status=201)

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        item = self.get_object()
        return Response(idempotent(request.user, request.headers.get('Idempotency-Key'), f'reservation.cancel:{pk}', {},
            lambda: service.cancel_reservation(request.user, item.pk)))

    @action(detail=True, methods=['post'])
    def collect(self, request, pk=None):
        item = self.get_object()
        def execute():
            require(item.status == 'ready' and item.copy_id, '预约尚不可取书')
            return service.borrow(request.user, item.reader_id, item.copy_id)
        return Response(idempotent(request.user, request.headers.get('Idempotency-Key'), f'reservation.collect:{pk}', {}, execute))


class FineViewSet(OwnedReadViewSet):
    queryset = m.Fine.objects.select_related('loan').all()
    serializer_class = s.FineSerializer
    owner_field = 'loan__reader'

    @extend_schema(request=s.FineAdjustmentSerializer)
    @action(detail=True, methods=['post'], permission_classes=[AdminOnly])
    def adjust(self, request, pk=None):
        data = validated(s.FineAdjustmentSerializer, request)
        def execute():
            fine = get_object_or_404(m.Fine.objects.select_for_update(), pk=pk)
            require(data['amount'] >= fine.paid_amount, '调整后金额不能小于已缴金额；退款需单独线下处理')
            previous = str(fine.amount)
            fine.amount = data['amount']
            if 'assessed_days' in data:
                fine.assessed_days = data['assessed_days']
            fine.save()
            audit(request.user, 'fine.adjust', fine, before=previous, after=str(fine.amount), reason=data['reason'])
            return s.FineSerializer(fine).data
        return Response(idempotent(request.user, request.headers.get('Idempotency-Key'), f'fine.adjust:{pk}', request.data, execute))


class PaymentViewSet(OwnedReadViewSet):
    queryset = m.Payment.objects.all()
    serializer_class = s.PaymentSerializer

    @extend_schema(request=s.FinePaymentSerializer)
    def create(self, request):
        data = validated(s.FinePaymentSerializer, request)
        return Response(idempotent(request.user, request.headers.get('Idempotency-Key'), 'payment.create', request.data,
            lambda: payments.create_payment(request.user, data['fine'])), status=201)

    @action(detail=True, methods=['post'])
    def simulate(self, request, pk=None):
        item = self.get_object()
        require(settings.SIMULATION_ENABLED, '模拟支付已禁用')
        return Response(payments.settle(item.pk, request.user))

    @action(detail=True, methods=['post'], permission_classes=[AdminOnly])
    def offline(self, request, pk=None):
        item = self.get_object()
        return Response(payments.settle(item.pk, request.user))

    @extend_schema(request=s.CallbackSerializer)
    @action(detail=False, methods=['post'], permission_classes=[permissions.AllowAny], authentication_classes=[])
    def callback(self, request):
        data = validated(s.CallbackSerializer, request)
        return Response(payments.callback(data['reference'], data['amount'], data['timestamp'], data['signature']))


class CreditViewSet(OwnedReadViewSet):
    queryset = m.CreditEntry.objects.all()
    serializer_class = s.CreditEntrySerializer


class DepositViewSet(OwnedReadViewSet):
    queryset = m.DepositEntry.objects.all()
    serializer_class = s.DepositEntrySerializer


class NotificationViewSet(OwnedReadViewSet):
    queryset = m.Notification.objects.all()
    serializer_class = s.NotificationSerializer

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return self.queryset.none()
        return self.queryset.filter(reader=self.request.user)

    @action(detail=True, methods=['post'])
    def read(self, request, pk=None):
        item = self.get_object()
        if not item.read_at:
            item.read_at = timezone.now()
            item.save()
        return Response(self.get_serializer(item).data)
