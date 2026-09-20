from drf_spectacular.utils import extend_schema
from rest_framework.decorators import action
from rest_framework.response import Response
from library import models as m
from library.services import circulation as service
from library.services.common import idempotent, require
from . import serializers as s
from .auth import validated
from .base import OwnedReadViewSet


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
