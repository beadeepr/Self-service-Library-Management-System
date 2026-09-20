from django.db import transaction
from drf_spectacular.utils import extend_schema, OpenApiTypes
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from library import models as m
from library.services.common import audit, idempotent
from .auth import validated
from .common import AdminOnly
from .serializers import BookSerializer, UserSerializer


class CatalogueRecordSerializer(serializers.Serializer):
    isbn = serializers.CharField(max_length=20)
    title = serializers.CharField(max_length=200)
    author = serializers.CharField(max_length=150)
    publisher = serializers.CharField(max_length=150, required=False, default='')
    category_code = serializers.CharField(max_length=30)
    category_name = serializers.CharField(max_length=100)
    call_number = serializers.CharField(max_length=50)
    price = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0)


class CatalogueImportSerializer(serializers.Serializer):
    records = CatalogueRecordSerializer(many=True)

    def validate_records(self, value):
        if not 1 <= len(value) <= 500:
            raise serializers.ValidationError('每批 1~500 条书目')
        if len({item['isbn'] for item in value}) != len(value):
            raise serializers.ValidationError('批次内 ISBN 不可重复')
        return value


class IntegrationViewSet(viewsets.GenericViewSet):
    serializer_class = CatalogueImportSerializer
    permission_classes = [AdminOnly]

    @extend_schema(request=CatalogueImportSerializer, responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=['post'], url_path='catalogue-import')
    def catalogue_import(self, request):
        data = validated(CatalogueImportSerializer, request)
        def execute():
            ids = []
            for row in data['records']:
                values = dict(row)
                category, _ = m.Category.objects.get_or_create(code=values.pop('category_code'), defaults={'name': values.pop('category_name')})
                isbn = values.pop('isbn')
                book, created = m.Book.objects.update_or_create(isbn=isbn, defaults={**values, 'category': category})
                audit(request.user, 'integration.catalogue', book, created=created)
                ids.append(book.pk)
            return {'book_ids': ids, 'count': len(ids)}
        return Response(idempotent(request.user, request.headers.get('Idempotency-Key'), 'integration.catalogue', request.data, execute))

    @extend_schema(responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=['get'])
    def capabilities(self, request):
        return Response({'version': 'v1', 'catalogue': '/api/v1/books/', 'copies': '/api/v1/copies/',
            'reader_directory': '/api/v1/readers/', 'circulation': '/api/v1/loans/',
            'catalogue_import': '/api/v1/integrations/catalogue-import/',
            'offline_reconciliation': '/api/v1/offline/sync/',
            'city_platform': {'status': 'extension', 'export': '/api/v1/reports/summary/'},
            'credit_provider': {'status': 'extension'}, 'seat_booking': {'status': 'extension'},
            'authentication': 'Bearer JWT', 'encoding': 'UTF-8', 'dates': 'ISO-8601'})
