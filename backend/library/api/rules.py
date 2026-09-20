from rest_framework import mixins, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from library.services.common import rules
from django.db import transaction
from rest_framework import viewsets
from library import models as m
from library.services.common import audit
from . import serializers as s
from .common import AdminOnly


class RuleViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet):
    queryset = m.Rule.objects.all()
    serializer_class = s.RuleSerializer
    permission_classes = [AdminOnly]

    @action(detail=False, methods=['get'], permission_classes=[permissions.IsAuthenticated])
    def current(self, request):
        return Response(self.get_serializer(rules()).data)

    def get_queryset(self):
        rules()
        return super().get_queryset()

    def perform_update(self, serializer):
        with transaction.atomic():
            obj = serializer.save()
            audit(self.request.user, 'rules.update', obj)
