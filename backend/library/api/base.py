from django.db import transaction
from rest_framework import viewsets
from rest_framework.response import Response
from library.services.common import audit, is_admin
from .common import AdminOnly


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
