"""Explicit schemas for action endpoints; CRUD schemas come from ModelSerializers."""
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiTypes, OpenApiParameter
from . import serializers as s
from .auth import AuthViewSet
from .resources import BookViewSet, BranchViewSet, CopyViewSet, ReaderViewSet, ActivityViewSet
from .circulation import LoanViewSet, ReservationViewSet, PaymentViewSet, NotificationViewSet, FineViewSet
from .operations import DeviceViewSet, VisitViewSet, TransferViewSet, AlertViewSet, WorkOrderViewSet, InventoryViewSet, OfflineViewSet
from .reports import ReportViewSet
from .integration import IntegrationViewSet, CatalogueImportSerializer

KEY = OpenApiParameter('Idempotency-Key', str, OpenApiParameter.HEADER, required=True,
    description='同一用户重试必须复用此键和相同请求体；新操作使用新键，最长 128 字符。')


def actions(view, definitions):
    annotations = {}
    for name, (body, keyed) in definitions.items():
        creates = (name == 'create' and view in [ReservationViewSet, PaymentViewSet, TransferViewSet, InventoryViewSet]) or (
            (view, name) in [(BookViewSet, 'intake'), (LoanViewSet, 'borrow'), (VisitViewSet, 'help')])
        responses = {201 if creates else 200: OpenApiTypes.OBJECT}
        if view == LoanViewSet and name == 'borrow':
            responses[200] = OpenApiTypes.OBJECT  # StockUnavailable uses HTTP 200/code 4001.
        annotations[name] = extend_schema(request=body, responses=responses,
            parameters=[KEY] if keyed else [])
    extend_schema_view(**annotations)(view)


actions(AuthViewSet, {
    'captcha': (None, False), 'sms_code': (s.CodeRequestSerializer, False), 'login': (s.LoginSerializer, False),
    'sms_login': (s.SmsLoginSerializer, False), 'qr_challenge': (s.EmptySerializer, False),
    'qr_confirm': (s.QrConfirmSerializer, False), 'qr_poll': (s.QrPollSerializer, False),
})
actions(BookViewSet, {'intake': (s.IntakeSerializer, True)})
extend_schema_view(search=extend_schema(parameters=[OpenApiParameter('q', str)],
    responses=s.BookSerializer(many=True)))(BookViewSet)
actions(BranchViewSet, {'occupancy': (None, False)})
actions(CopyViewSet, {'disinfect': (s.EmptySerializer, False), 'shelve': (s.ShelfSerializer, False), 'set_status': (s.CopyStatusSerializer, False)})
actions(ReaderViewSet, {'password': (s.PasswordSerializer, False), 'phone': (s.SmsLoginSerializer, False),
    'verify_identity': (s.IdentitySerializer, False), 'manage': (s.ReaderAdminSerializer, True)})
actions(ActivityViewSet, {'enroll': (s.EmptySerializer, False)})
actions(LoanViewSet, {'borrow': (s.BorrowSerializer, True), 'return_book': (s.ReturnSerializer, True),
    'renew': (s.EmptySerializer, True), 'remind': (s.EmptySerializer, False)})
for method, body in [('return_by_id', s.CirculationReturnSerializer), ('renew_by_id', s.CirculationRenewSerializer)]:
    setattr(LoanViewSet, method, extend_schema(request=body, responses=OpenApiTypes.OBJECT,
        parameters=[KEY])(getattr(LoanViewSet, method)))
actions(ReservationViewSet, {'create': (s.ReserveSerializer, True), 'cancel': (s.EmptySerializer, True), 'collect': (s.EmptySerializer, True)})
actions(PaymentViewSet, {'create': (s.FinePaymentSerializer, True), 'simulate': (s.EmptySerializer, False),
    'offline': (s.EmptySerializer, False), 'callback': (s.CallbackSerializer, False)})
actions(NotificationViewSet, {'read': (s.EmptySerializer, False)})
actions(FineViewSet, {'adjust': (s.FineAdjustmentSerializer, True)})
actions(DeviceViewSet, {'events': (s.DeviceEventInputSerializer, False), 'command': (s.CommandSerializer, True)})
actions(VisitViewSet, {'access': (s.AccessSerializer, True), 'help': (s.HelpSerializer, False)})
actions(TransferViewSet, {'create': (s.TransferInputSerializer, True), 'transition': (s.TransferActionSerializer, True)})
actions(AlertViewSet, {'transition': (s.AlertActionSerializer, False)})
actions(WorkOrderViewSet, {'transition': (s.WorkTransitionSerializer, False)})
actions(InventoryViewSet, {'create': (s.InventoryInputSerializer, False)})
actions(OfflineViewSet, {'sync': (s.OfflineBatchSerializer, False)})
actions(ReportViewSet, {'summary': (None, False)})
actions(IntegrationViewSet, {'catalogue_import': (CatalogueImportSerializer, True), 'capabilities': (None, False)})
extend_schema_view(export=extend_schema(responses={(200, 'text/csv'): OpenApiTypes.STR}))(ReportViewSet)
