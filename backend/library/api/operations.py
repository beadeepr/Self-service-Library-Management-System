from django.db import transaction
from django.shortcuts import get_object_or_404
from django.http import Http404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from library import models as m
from library.services import operations as service, circulation
from library.services.common import audit, idempotent, is_admin, require
from . import serializers as s
from .auth import validated
from .common import AdminOnly, StaffOnly, OperatorOnly
from .resources import AuditedModelViewSet
from .circulation import OwnedReadViewSet


class DeviceViewSet(AuditedModelViewSet):
    queryset = m.Device.objects.all()
    serializer_class = s.DeviceSerializer
    permission_classes = [StaffOnly]
    filterset_fields = ['branch', 'kind', 'online']

    def get_permissions(self):
        classes = [StaffOnly] if self.action in ['list', 'retrieve'] else [OperatorOnly]
        return [permission() for permission in classes]

    @extend_schema(request=s.DeviceEventInputSerializer)
    @action(detail=True, methods=['post'])
    def events(self, request, pk=None):
        data = validated(s.DeviceEventInputSerializer, request)
        return Response(service.ingest(request.user, pk, data['event_id'], data['kind'], data['payload']))

    @extend_schema(request=s.CommandSerializer)
    @action(detail=True, methods=['post'])
    def command(self, request, pk=None):
        data = validated(s.CommandSerializer, request)
        return Response(idempotent(request.user, request.headers.get('Idempotency-Key'), f'device.command:{pk}', request.data,
            lambda: service.command(request.user, pk, data['command'], data['reason'])))


class DeviceEventViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = m.DeviceEvent.objects.all()
    serializer_class = s.DeviceEventSerializer
    permission_classes = [StaffOnly]
    filterset_fields = ['device', 'kind']


class DeviceCommandViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = m.DeviceCommand.objects.all()
    serializer_class = s.DeviceCommandSerializer
    permission_classes = [StaffOnly]
    filterset_fields = ['device', 'status']


class AlertViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = m.Alert.objects.all()
    serializer_class = s.AlertSerializer
    permission_classes = [StaffOnly]
    filterset_fields = ['branch', 'severity', 'status', 'kind']

    @extend_schema(request=s.AlertActionSerializer)
    @action(detail=True, methods=['post'])
    def transition(self, request, pk=None):
        data = validated(s.AlertActionSerializer, request)
        with transaction.atomic():
            item = get_object_or_404(m.Alert.objects.select_for_update(), pk=pk)
            expected = {'open': 'acknowledged', 'acknowledged': 'resolved'}
            require(expected.get(item.status) == data['status'], '告警必须先确认再关闭')
            if data['status'] == 'resolved':
                require(data.get('resolution'), '关闭告警必须填写处置结果')
            item.status = data['status']
            item.resolution = data.get('resolution', '')
            item.save()
            audit(request.user, 'alert.transition', item, **data)
        return Response(self.get_serializer(item).data)


class VisitViewSet(OwnedReadViewSet):
    queryset = m.Visit.objects.all()
    serializer_class = s.VisitSerializer
    filterset_fields = ['branch']

    @extend_schema(request=s.AccessSerializer)
    @action(detail=False, methods=['post'])
    def access(self, request):
        data = validated(s.AccessSerializer, request)
        return Response(idempotent(request.user, request.headers.get('Idempotency-Key'), 'visit.access', request.data,
            lambda: service.access(request.user, data.get('reader', request.user.pk), data['branch'], data['direction'], data['method'])))

    @extend_schema(request=s.HelpSerializer)
    @action(detail=False, methods=['post'])
    def help(self, request):
        data = validated(s.HelpSerializer, request)
        item = service.raise_alert(data['branch'], 'help', data['message'], 'critical')
        audit(request.user, 'emergency.help', item)
        return Response({'id': item.pk, 'status': item.status}, status=201)


class TransferViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = m.Transfer.objects.all()
    serializer_class = s.TransferSerializer
    permission_classes = [StaffOnly]
    filterset_fields = ['status', 'source', 'destination']

    @extend_schema(request=s.TransferInputSerializer)
    def create(self, request):
        data = validated(s.TransferInputSerializer, request)
        return Response(idempotent(request.user, request.headers.get('Idempotency-Key'), 'transfer.create', request.data,
            lambda: service.plan_transfer(request.user, data['copy'], data['destination'], data['route'], data['schedule'])), status=201)

    @extend_schema(request=s.TransferActionSerializer)
    @action(detail=True, methods=['post'])
    def transition(self, request, pk=None):
        data = validated(s.TransferActionSerializer, request)
        require(data['action'] != 'redirect' or 'destination' in data, '改派需要指定目标网点')
        return Response(idempotent(request.user, request.headers.get('Idempotency-Key'), f'transfer.transition:{pk}', request.data,
            lambda: service.transition_transfer(request.user, pk, data['action'], data.get('destination'))))


class WorkOrderViewSet(AuditedModelViewSet):
    queryset = m.WorkOrder.objects.all()
    serializer_class = s.WorkOrderSerializer
    permission_classes = [StaffOnly]
    filterset_fields = ['branch', 'assignee', 'status', 'kind']
    http_method_names = ['get', 'post', 'patch', 'head', 'options']

    def perform_update(self, serializer):
        require(serializer.instance.status in ['open', 'in_progress'], '已完成工单不可修改基本信息')
        super().perform_update(serializer)

    @extend_schema(request=s.WorkTransitionSerializer)
    @action(detail=True, methods=['post'])
    def transition(self, request, pk=None):
        data = validated(s.WorkTransitionSerializer, request)
        with transaction.atomic():
            item = get_object_or_404(m.WorkOrder.objects.select_for_update(), pk=pk)
            expected = {'open': 'in_progress', 'in_progress': 'completed', 'completed': 'reviewed'}
            require(expected.get(item.status) == data['status'], '工单状态流转顺序错误')
            if data['status'] == 'completed':
                require(data.get('result'), '请填写维修或巡检结果')
                item.result = data['result']
                item.completed_at = timezone.now()
            if data['status'] == 'reviewed':
                require(is_admin(request.user), '仅管理员可复核工单')
                require(data.get('review'), '请填写复核意见')
                item.review = data['review']
            item.status = data['status']
            item.save()
            audit(request.user, 'workorder.transition', item, **data)
        return Response(self.get_serializer(item).data)


class InventoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = m.Inventory.objects.all()
    serializer_class = s.InventorySerializer
    permission_classes = [StaffOnly]

    @extend_schema(request=s.InventoryInputSerializer)
    def create(self, request):
        data = validated(s.InventoryInputSerializer, request)
        return Response(service.inventory(request.user, data['branch'], data['shelf'], data['observed']), status=201)


class AuditViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = m.AuditLog.objects.all()
    serializer_class = s.AuditLogSerializer
    permission_classes = [AdminOnly]
    filterset_fields = ['actor', 'action', 'resource']


class OfflineViewSet(viewsets.GenericViewSet):
    serializer_class = s.OfflineBatchSerializer
    permission_classes = [AdminOnly]

    @action(detail=False, methods=['post'])
    def sync(self, request):
        data = validated(s.OfflineBatchSerializer, request)
        results = []
        for item in data['transactions']:
            try:
                def execute():
                    require(item['occurred_at'] <= timezone.now(), '离线交易时间不能在未来')
                    if item['kind'] == 'borrow':
                        require('reader' in item and 'copy' in item, '借书需要 reader、copy')
                        result = circulation.borrow(request.user, item['reader'], item['copy'], occurred_at=item['occurred_at'])
                    else:
                        require('loan' in item and 'branch' in item, '还书需要 loan、branch')
                        result = circulation.return_book(request.user, item['loan'], item['branch'], occurred_at=item['occurred_at'])
                    audit(request.user, 'offline.reconcile', request.user, event_id=str(item['event_id']), occurred_at=item['occurred_at'].isoformat())
                    return result
                result = idempotent(request.user, f'offline:{item["event_id"]}', 'offline.sync', item, execute)
                results.append({'event_id': item['event_id'], 'status': 'applied', 'result': result})
            except (APIException, Http404) as exc:
                results.append({'event_id': item['event_id'], 'status': 'conflict', 'detail': getattr(exc, 'detail', str(exc))})
        return Response({'results': results})
