from django.conf import settings
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from library import models as m
from library.services import fine_service as payments
from library.services.common import audit, idempotent, require
from . import serializers as s
from .auth import validated
from .common import AdminOnly
from .base import OwnedReadViewSet


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
