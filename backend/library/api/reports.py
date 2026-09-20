import csv
import io
from django.db.models import Count, Sum, F
from django.db.models.functions import TruncDate
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from library import models as m
from library.services.common import audit
from .common import AdminOnly, StaffOnly
from .serializers import EmptySerializer


class ReportViewSet(viewsets.GenericViewSet):
    serializer_class = EmptySerializer
    permission_classes = [AdminOnly]

    @action(detail=False, methods=['get'], permission_classes=[StaffOnly])
    def summary(self, request):
        now = timezone.now()
        return Response({
            'copies_by_status': list(m.Copy.objects.values('status').annotate(count=Count('id')).order_by('status')),
            'categories': list(m.Copy.objects.values('book__category__name').annotate(count=Count('id')).order_by('book__category__name')),
            'loan_trend': list(m.Loan.objects.annotate(day=TruncDate('borrowed_at')).values('day').annotate(count=Count('id')).order_by('day')),
            'popular_books': list(m.Loan.objects.values('copy__book_id', 'copy__book__title').annotate(count=Count('id')).order_by('-count')[:10]),
            'reader_activity': list(m.Loan.objects.values('reader_id').annotate(count=Count('id')).order_by('-count')[:20]),
            'occupancy': m.Visit.objects.filter(exited_at=None).count(),
            'visits_trend': list(m.Visit.objects.annotate(day=TruncDate('entered_at')).values('day').annotate(count=Count('id')).order_by('day')),
            'devices_total': m.Device.objects.count(), 'devices_online': m.Device.objects.filter(online=True).count(),
            'device_events': list(m.DeviceEvent.objects.values('device_id').annotate(count=Count('id')).order_by('-count')),
            'open_alerts': m.Alert.objects.exclude(status='resolved').count(),
            'fine_income': m.Payment.objects.filter(status='paid').aggregate(total=Sum('amount'))['total'] or 0,
            'deposit_balance': m.User.objects.aggregate(total=Sum('deposit'))['total'] or 0,
            'overdue_loans': m.Loan.objects.filter(returned_at=None, due_at__lt=now).count(),
            'late_shelving': m.Copy.objects.filter(status='processing', shelving_due_at__lt=now).count(),
            'overdue_workorders': m.WorkOrder.objects.filter(status__in=['open', 'in_progress'], due_at__lt=now).count(),
            'workorders_on_time': m.WorkOrder.objects.filter(completed_at__lte=F('due_at')).count(),
            'annual_costs': list(m.OperationRecord.objects.filter(kind='cost').values('occurred_on__year', 'branch_id').annotate(total=Sum('amount')).order_by('occurred_on__year')),
            'labor_hours': m.OperationRecord.objects.filter(kind='labor').aggregate(total=Sum('hours'))['total'] or 0,
        })

    @action(detail=False, methods=['get'])
    def export(self, request):
        stream = io.StringIO()
        writer = csv.writer(stream)
        writer.writerow(['id', 'isbn', 'title', 'author', 'copies'])
        for book in m.Book.objects.annotate(total=Count('copies')).iterator():
            # Guard spreadsheet formula execution in exported user-controlled strings.
            safe = lambda value: "'"+str(value) if str(value).startswith(('=', '+', '-', '@', '\t', '\r')) else value
            writer.writerow([book.pk, safe(book.isbn), safe(book.title), safe(book.author), book.total])
        audit(request.user, 'report.export', request.user, kind='catalogue')
        response = HttpResponse('\ufeff'+stream.getvalue(), content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename="catalogue.csv"'
        return response
