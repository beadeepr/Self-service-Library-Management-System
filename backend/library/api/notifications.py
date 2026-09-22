from .common import PublicReadAdminWrite
from django.utils import timezone
from rest_framework.decorators import action
from rest_framework.response import Response
from library import models as m
from library.services.common import is_admin
from . import serializers as s
from .base import AuditedModelViewSet, OwnedReadViewSet


class AnnouncementViewSet(AuditedModelViewSet):
    queryset = m.Announcement.objects.all()
    serializer_class = s.AnnouncementSerializer
    permission_classes = [PublicReadAdminWrite]

    def get_queryset(self):
        return self.queryset if is_admin(self.request.user) else self.queryset.filter(published=True)



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
