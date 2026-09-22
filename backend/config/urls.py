from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView
from rest_framework.routers import DefaultRouter
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.views import TokenRefreshView, TokenBlacklistView
from library.api.auth import AuthViewSet
from library.api.catalog import BranchViewSet, CategoryViewSet, BookViewSet, CopyViewSet
from library.api.readers import ReaderViewSet, ConsentViewSet, CreditViewSet, DepositViewSet
from library.api.rules import RuleViewSet
from library.api.notifications import AnnouncementViewSet, NotificationViewSet
from library.api.reservations import ReservationViewSet
from library.api.fines import FineViewSet, PaymentViewSet
from library.api.circulation import LoanViewSet
from library.api.offline import OfflineViewSet
from library.api.resources import OperationRecordViewSet, ActivityViewSet
from library.api.operations import (DeviceViewSet, DeviceEventViewSet, DeviceCommandViewSet, AlertViewSet,
    VisitViewSet, TransferViewSet, WorkOrderViewSet, InventoryViewSet, AuditViewSet)
from library.api.reports import ReportViewSet
from library.api.integration import IntegrationViewSet
from library.api import schema  # Register action contracts before URL resolution.
from library.api.health import readiness

router = DefaultRouter()
for prefix, view in [
    ('auth', AuthViewSet), ('readers', ReaderViewSet), ('branches', BranchViewSet),
    ('categories', CategoryViewSet), ('books', BookViewSet), ('copies', CopyViewSet),
    ('rules', RuleViewSet), ('loans', LoanViewSet), ('reservations', ReservationViewSet),
    ('fines', FineViewSet), ('payments', PaymentViewSet), ('credit-entries', CreditViewSet),
    ('deposit-entries', DepositViewSet),
    ('notifications', NotificationViewSet), ('announcements', AnnouncementViewSet), ('consents', ConsentViewSet),
    ('devices', DeviceViewSet), ('device-events', DeviceEventViewSet), ('device-commands', DeviceCommandViewSet),
    ('alerts', AlertViewSet), ('visits', VisitViewSet), ('transfers', TransferViewSet),
    ('work-orders', WorkOrderViewSet), ('inventories', InventoryViewSet), ('operations', OperationRecordViewSet),
    ('activities', ActivityViewSet), ('audit-logs', AuditViewSet), ('offline', OfflineViewSet), ('reports', ReportViewSet),
    ('integrations', IntegrationViewSet),
]:
    router.register(prefix, view, basename=prefix)

urlpatterns = [
    path('health/', lambda request: JsonResponse({'status': 'ok'})),
    path('health/ready/', readiness),
    path('admin/', admin.site.urls),
    path('api/auth/register/', AuthViewSet.as_view({'post': 'register'})),
    path('api/auth/login/', AuthViewSet.as_view({'post': 'login'})),
    path('api/auth/refresh/', TokenRefreshView.as_view()),
    path('api/books/search/', BookViewSet.as_view({'get': 'search'})),
    path('api/circulation/borrow/', LoanViewSet.as_view({'post': 'borrow'})),
    path('api/circulation/return/', LoanViewSet.as_view({'post': 'return_by_id'})),
    path('api/circulation/renew/', LoanViewSet.as_view({'post': 'renew_by_id'})),
    path('api/circulation/loans/', LoanViewSet.as_view({'get': 'list'})),
    path('api/rules/current/', RuleViewSet.as_view({'get': 'current'}, permission_classes=[IsAuthenticated])),
    path('api/offline/sync/', OfflineViewSet.as_view({'post': 'sync'})),
    path('api/v1/auth/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('api/v1/auth/logout/', TokenBlacklistView.as_view(), name='token_logout'),
    path('api/v1/', include(router.urls)),
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
]
