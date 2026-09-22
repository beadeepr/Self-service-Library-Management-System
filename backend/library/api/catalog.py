from django.db.models import Count, Q
from rest_framework import mixins
from library.services import catalog_service as circulation
from .common import StaffOnly, PublicReadAdminWrite
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from library import models as m
from library.services.common import audit, idempotent, require
from . import serializers as s
from .auth import validated
from .common import AdminOnly
from .base import AuditedModelViewSet


class BranchViewSet(AuditedModelViewSet):
    queryset = m.Branch.objects.all()
    serializer_class = s.BranchSerializer
    permission_classes = [PublicReadAdminWrite]

    @action(detail=True, methods=['get'])
    def occupancy(self, request, pk=None):
        branch = self.get_object()
        count = m.Visit.objects.filter(branch=branch, exited_at=None).count()
        return Response({'branch': branch.pk, 'occupancy': count, 'capacity': branch.capacity,
                         'seats': branch.seats, 'estimated_free_seats': max(0, branch.seats-count)})



class CategoryViewSet(AuditedModelViewSet):
    queryset = m.Category.objects.all()
    serializer_class = s.CategorySerializer
    permission_classes = [PublicReadAdminWrite]



class BookViewSet(AuditedModelViewSet):
    queryset = m.Book.objects.select_related('category').annotate(
        total_count=Count('copies'), available_count=Count('copies', filter=Q(copies__status='available')),
        loaned_count=Count('copies', filter=Q(copies__status='loaned'))).order_by('-id')
    serializer_class = s.BookSerializer
    permission_classes = [PublicReadAdminWrite]
    search_fields = ['title', 'isbn', 'author', 'category__code', 'call_number']
    filterset_fields = ['isbn', 'category', 'author', 'active']
    ordering_fields = ['id', 'title', 'price']

    @action(detail=False, methods=['get'])
    def search(self, request):
        return self.list(request)

    def get_queryset(self):
        queryset = super().get_queryset()
        query = self.request.query_params.get('q', '').strip()
        if query:
            queryset = queryset.filter(Q(title__icontains=query) | Q(isbn__icontains=query) |
                Q(author__icontains=query) | Q(category__code__icontains=query) |
                Q(call_number__icontains=query))
        return queryset

    @extend_schema(request=s.IntakeSerializer)
    @action(detail=True, methods=['post'], permission_classes=[AdminOnly])
    def intake(self, request, pk=None):
        book = self.get_object()
        data = validated(s.IntakeSerializer, request)
        def execute():
            copies = [m.Copy.objects.create(book=book, branch=data['branch'], shelf=data['shelf']) for _ in range(data['quantity'])]
            audit(request.user, 'book.intake', book, quantity=len(copies))
            return {'copies': s.CopySerializer(copies, many=True).data}
        return Response(idempotent(request.user, request.headers.get('Idempotency-Key'), f'book.intake:{pk}', request.data, execute), status=201)



class CopyViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = m.Copy.objects.select_related('book', 'branch').all()
    serializer_class = s.CopySerializer
    permission_classes = [PublicReadAdminWrite]
    filterset_fields = ['book', 'branch', 'status', 'rfid', 'shelf']

    @action(detail=True, methods=['post'], permission_classes=[StaffOnly])
    def disinfect(self, request, pk=None):
        with transaction.atomic():
            copy = get_object_or_404(m.Copy.objects.select_for_update(), pk=pk)
            require(copy.status == 'processing', '仅待处理图书可登记消毒')
            copy.disinfected_at = timezone.now()
            copy.save()
            audit(request.user, 'copy.disinfect', copy)
        return Response(self.get_serializer(copy).data)

    @extend_schema(request=s.ShelfSerializer)
    @action(detail=True, methods=['post'], permission_classes=[StaffOnly])
    def shelve(self, request, pk=None):
        data = validated(s.ShelfSerializer, request)
        return Response(circulation.shelve(request.user, pk, data['shelf']))

    @extend_schema(request=s.CopyStatusSerializer)
    @action(detail=True, methods=['post'], permission_classes=[AdminOnly], url_path='set-status')
    def set_status(self, request, pk=None):
        data = validated(s.CopyStatusSerializer, request)
        with transaction.atomic():
            copy = get_object_or_404(m.Copy.objects.select_for_update(), pk=pk)
            require(copy.status not in ['loaned', 'reserved', 'transit'], '须先结束借阅、预约或配送流程')
            require(not m.Transfer.objects.filter(copy=copy, status='planned').exists(), '图书已有待发货任务')
            copy.status = data['status']
            copy.save()
            audit(request.user, 'copy.status', copy, **data)
        return Response(self.get_serializer(copy).data)
