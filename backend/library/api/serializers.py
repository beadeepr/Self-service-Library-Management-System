from django.utils import timezone
from rest_framework import serializers
from library import models as m
from library.services.authentication import validate_secret


class UserSerializer(serializers.ModelSerializer):
    def update(self, instance, validated_data):
        fields = ['first_name', 'avatar', 'contact']
        changes = {key: value for key, value in validated_data.items() if key in fields}
        for key, value in changes.items():
            setattr(instance, key, value)
        if changes:
            instance.save(update_fields=list(changes))
        return instance

    credit_level = serializers.SerializerMethodField()

    def get_credit_level(self, obj) -> str:
        from library.services.common import rules
        if obj.credit < min(40, rules().minimum_credit):
            return 'untrusted'
        if obj.frozen or obj.credit < rules().minimum_credit:
            return 'restricted'
        return 'normal'

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        if request and request.user.pk != instance.pk:
            data['phone'] = instance.phone[:3]+'****'+instance.phone[-4:]
        return data

    class Meta:
        model = m.User
        fields = ['id', 'phone', 'first_name', 'avatar', 'contact', 'role', 'verified', 'credit', 'credit_level', 'frozen', 'deposit', 'is_active']
        read_only_fields = ['id', 'phone', 'role', 'verified', 'credit', 'frozen', 'deposit', 'is_active']


class BookSerializer(serializers.ModelSerializer):
    available_count = serializers.IntegerField(read_only=True)
    total_count = serializers.IntegerField(read_only=True)
    loaned_count = serializers.IntegerField(read_only=True)
    can_reserve = serializers.SerializerMethodField()

    def get_can_reserve(self, obj) -> bool:
        # Branch-specific eligibility is rechecked by the reservation service.
        return bool(obj.active and getattr(obj, 'available_count', 0) == 0 and getattr(obj, 'loaned_count', 0) > 0)

    class Meta:
        model = m.Book
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at']


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = m.Category
        fields = '__all__'

    def validate_parent(self, value):
        visited = set()
        current = value
        while current:
            if current.pk in visited or (self.instance and current.pk == self.instance.pk):
                raise serializers.ValidationError('分类树不可循环引用')
            visited.add(current.pk)
            current = current.parent
        return value


class RuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = m.Rule
        fields = '__all__'
        read_only_fields = ['name']

    def validate_holidays(self, value):
        import datetime
        try:
            if not isinstance(value, list) or len(value) > 3660:
                raise ValueError()
            for item in value:
                datetime.date.fromisoformat(item)
        except (ValueError, TypeError):
            raise serializers.ValidationError('节假日应为 YYYY-MM-DD 字符串列表')
        return value


def model_serializer(model, readonly=()):
    meta = type('Meta', (), {'model': model, 'fields': '__all__',
        'read_only_fields': ['id', 'created_at', 'updated_at', *readonly]})
    return type(f'{model.__name__}Serializer', (serializers.ModelSerializer,), {'Meta': meta, '__module__': __name__})


BranchSerializer = model_serializer(m.Branch)
CopySerializer = model_serializer(m.Copy, ['rfid', 'status', 'disinfected_at', 'shelving_due_at'])
LoanSerializer = model_serializer(m.Loan)
ReservationSerializer = model_serializer(m.Reservation)
FineSerializer = model_serializer(m.Fine)
PaymentSerializer = model_serializer(m.Payment)
CreditEntrySerializer = model_serializer(m.CreditEntry)
DepositEntrySerializer = model_serializer(m.DepositEntry)
NotificationSerializer = model_serializer(m.Notification)
AnnouncementSerializer = model_serializer(m.Announcement)
ConsentSerializer = model_serializer(m.Consent, ['reader'])
DeviceSerializer = model_serializer(m.Device, ['online', 'last_seen', 'shadow'])
DeviceEventSerializer = model_serializer(m.DeviceEvent)
DeviceCommandSerializer = model_serializer(m.DeviceCommand)
AlertSerializer = model_serializer(m.Alert)
VisitSerializer = model_serializer(m.Visit)
TransferSerializer = model_serializer(m.Transfer)
InventorySerializer = model_serializer(m.Inventory)
AuditLogSerializer = model_serializer(m.AuditLog)
EnrollmentSerializer = model_serializer(m.Enrollment)


class OperationRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = m.OperationRecord
        fields = '__all__'

    def validate(self, attrs):
        kind = attrs.get('kind', getattr(self.instance, 'kind', None))
        expires = attrs.get('expires_at', getattr(self.instance, 'expires_at', None))
        if kind == 'video' and not expires:
            raise serializers.ValidationError('视频索引必须设置过期时间；本接口不存储视频文件')
        return attrs


class WorkOrderSerializer(serializers.ModelSerializer):
    class Meta:
        model = m.WorkOrder
        fields = '__all__'
        read_only_fields = ['status', 'result', 'review', 'completed_at']

    def validate(self, attrs):
        assignee = attrs.get('assignee')
        if assignee and assignee.role not in ['admin', 'operator'] and not assignee.is_superuser:
            raise serializers.ValidationError('工单只能分配给管理员或运维人员')
        device = attrs.get('device', getattr(self.instance, 'device', None))
        branch = attrs.get('branch', getattr(self.instance, 'branch', None))
        if device and branch and device.branch_id != branch.pk:
            raise serializers.ValidationError('设备不属于此网点')
        return attrs


class ActivitySerializer(serializers.ModelSerializer):
    class Meta:
        model = m.Activity
        fields = '__all__'

    def validate_capacity(self, value):
        if self.instance and value < self.instance.enrollments.count():
            raise serializers.ValidationError('容量不能低于已报名人数')
        return value


class PhoneSerializer(serializers.Serializer):
    phone = serializers.RegexField(r'^1\d{10}$')


class CaptchaSerializer(serializers.Serializer):
    captcha_id = serializers.UUIDField()
    captcha_answer = serializers.CharField(max_length=20)


class CodeRequestSerializer(PhoneSerializer, CaptchaSerializer):
    purpose = serializers.ChoiceField(choices=['register', 'login', 'phone'])


class RegisterSerializer(PhoneSerializer):
    code = serializers.CharField(max_length=6)
    password = serializers.CharField(write_only=True, max_length=128)
    first_name = serializers.CharField(max_length=150, required=False, default='')

    def validate_password(self, value):
        validate_secret(value)
        return value


class LoginSerializer(PhoneSerializer):
    password = serializers.CharField(write_only=True, max_length=128)


class SmsLoginSerializer(PhoneSerializer):
    code = serializers.CharField(max_length=6)


class PasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, max_length=128)


class IdentitySerializer(serializers.Serializer):
    identity = serializers.RegexField(r'^\d{17}[0-9Xx]$', write_only=True)


class BorrowSerializer(serializers.Serializer):
    copy = serializers.IntegerField(min_value=1)
    reader = serializers.IntegerField(min_value=1, required=False)


class ReturnSerializer(serializers.Serializer):
    branch = serializers.IntegerField(min_value=1)
    damaged = serializers.BooleanField(default=False)


class CirculationReturnSerializer(ReturnSerializer):
    loan = serializers.IntegerField(min_value=1)


class CirculationRenewSerializer(serializers.Serializer):
    loan = serializers.IntegerField(min_value=1)


class ReserveSerializer(serializers.Serializer):
    book = serializers.IntegerField(min_value=1)
    branch = serializers.IntegerField(min_value=1)


class IntakeSerializer(serializers.Serializer):
    branch = serializers.PrimaryKeyRelatedField(queryset=m.Branch.objects.filter(active=True))
    quantity = serializers.IntegerField(min_value=1, max_value=500)
    shelf = serializers.CharField(max_length=100, required=False, default='')


class ShelfSerializer(serializers.Serializer):
    shelf = serializers.CharField(max_length=100)


class CopyStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=['withdrawn', 'lost', 'processing'])
    reason = serializers.CharField(max_length=255)


class ReaderAdminSerializer(serializers.Serializer):
    frozen = serializers.BooleanField(required=False)
    role = serializers.ChoiceField(choices=m.User.Role.choices, required=False)
    credit_delta = serializers.IntegerField(min_value=-200, max_value=200, required=False)
    deposit_delta = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    new_password = serializers.CharField(max_length=128, required=False, write_only=True)
    reason = serializers.CharField(max_length=255)


class FinePaymentSerializer(serializers.Serializer):
    fine = serializers.IntegerField(min_value=1)


class FineAdjustmentSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0)
    assessed_days = serializers.IntegerField(min_value=0, required=False)
    reason = serializers.CharField(max_length=255)


class CallbackSerializer(serializers.Serializer):
    reference = serializers.UUIDField()
    amount = serializers.RegexField(r'^\d{1,8}\.\d{2}$')
    timestamp = serializers.IntegerField()
    signature = serializers.CharField(max_length=64)


class DeviceEventInputSerializer(serializers.Serializer):
    event_id = serializers.UUIDField()
    kind = serializers.ChoiceField(choices=['heartbeat', 'telemetry', 'fault', 'smoke', 'help', 'security', 'rfid_exit', 'inventory'])
    payload = serializers.DictField(default=dict)


class CommandSerializer(serializers.Serializer):
    command = serializers.ChoiceField(choices=['power_on', 'power_off', 'restart', 'unlock', 'broadcast'])
    reason = serializers.CharField(max_length=255)


class AccessSerializer(serializers.Serializer):
    reader = serializers.IntegerField(min_value=1, required=False)
    branch = serializers.IntegerField(min_value=1)
    direction = serializers.ChoiceField(choices=['enter', 'exit'])
    method = serializers.ChoiceField(choices=['qr', 'card', 'face'], default='qr')


class HelpSerializer(serializers.Serializer):
    branch = serializers.PrimaryKeyRelatedField(queryset=m.Branch.objects.all())
    message = serializers.CharField(max_length=1000)


class TransferInputSerializer(serializers.Serializer):
    copy = serializers.IntegerField(min_value=1)
    destination = serializers.IntegerField(min_value=1)
    route = serializers.CharField(max_length=255)
    schedule = serializers.DateTimeField()


class TransferActionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=['ship', 'receive', 'cancel', 'redirect', 'return'])
    destination = serializers.IntegerField(min_value=1, required=False)


class WorkTransitionSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=['in_progress', 'completed', 'reviewed'])
    result = serializers.CharField(required=False)
    review = serializers.CharField(required=False)


class AlertActionSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=['acknowledged', 'resolved'])
    resolution = serializers.CharField(required=False)


class InventoryInputSerializer(serializers.Serializer):
    branch = serializers.IntegerField(min_value=1)
    shelf = serializers.CharField(max_length=100, required=False, default='')
    observed = serializers.ListField(child=serializers.UUIDField(), max_length=10000)


class OfflineItemSerializer(serializers.Serializer):
    event_id = serializers.UUIDField()
    kind = serializers.ChoiceField(choices=['borrow', 'return'])
    reader = serializers.IntegerField(min_value=1, required=False)
    copy = serializers.IntegerField(min_value=1, required=False)
    loan = serializers.IntegerField(min_value=1, required=False)
    branch = serializers.IntegerField(min_value=1, required=False)
    occurred_at = serializers.DateTimeField()


class OfflineBatchSerializer(serializers.Serializer):
    transactions = OfflineItemSerializer(many=True)

    def validate_transactions(self, value):
        if not 1 <= len(value) <= 100:
            raise serializers.ValidationError('每批 1~100 条记录')
        return value


class QrPollSerializer(serializers.Serializer):
    token = serializers.UUIDField()
    poll_secret = serializers.CharField(max_length=100)


class QrConfirmSerializer(serializers.Serializer):
    token = serializers.UUIDField()


class EmptySerializer(serializers.Serializer):
    pass
