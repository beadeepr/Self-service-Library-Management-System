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



from .base import AuditedModelViewSet
from .catalog import BranchViewSet, CategoryViewSet, BookViewSet, CopyViewSet
from .readers import ReaderViewSet, ConsentViewSet
from .rules import RuleViewSet
from .notifications import AnnouncementViewSet

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
