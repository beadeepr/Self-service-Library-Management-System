import uuid
from decimal import Decimal
from django.contrib.auth.models import AbstractUser
from django.core.validators import MinValueValidator, MaxValueValidator, RegexValidator
from django.db import models
from django.db.models import Q
from .fields import EncryptedCharField


class Record(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        ordering = ['-id']


class User(AbstractUser):
    REQUIRED_FIELDS = ['phone']
    class Role(models.TextChoices):
        READER = 'reader', '读者'
        ADMIN = 'admin', '管理员'
        OPERATOR = 'operator', '运维'
    phone = EncryptedCharField(max_length=11, unique=True, validators=[RegexValidator(r'^1\d{10}$', '手机号格式错误')])
    first_name = EncryptedCharField(max_length=150, blank=True)
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.READER)
    avatar = models.URLField(blank=True)
    contact = EncryptedCharField(max_length=200, blank=True)
    verified = models.BooleanField(default=False)
    identity_digest = models.CharField(max_length=64, unique=True, null=True, blank=True)
    credit = models.PositiveIntegerField(default=100, validators=[MaxValueValidator(200)])
    frozen = models.BooleanField(default=False)
    deposit = models.DecimalField(max_digits=10, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    failed_logins = models.PositiveIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)


class VerificationCode(Record):
    phone = EncryptedCharField(max_length=11)
    purpose = models.CharField(max_length=20, choices=[(v, v) for v in ['register', 'login', 'phone']])
    digest = models.CharField(max_length=128)
    expires_at = models.DateTimeField()
    attempts = models.PositiveIntegerField(default=0)
    consumed = models.BooleanField(default=False)


class LoginChallenge(Record):
    token = models.UUIDField(default=uuid.uuid4, unique=True)
    poll_digest = models.CharField(max_length=64)
    reader = models.ForeignKey(User, null=True, on_delete=models.CASCADE)
    expires_at = models.DateTimeField()
    consumed = models.BooleanField(default=False)


class Branch(Record):
    name = models.CharField(max_length=100)
    address = models.CharField(max_length=255)
    opening_time = models.TimeField(default='00:00')
    closing_time = models.TimeField(default='00:00')
    active = models.BooleanField(default=True)
    seats = models.PositiveIntegerField(default=15)
    capacity = models.PositiveIntegerField(default=100)
    area = models.DecimalField(max_digits=10, decimal_places=2, default=100, validators=[MinValueValidator(0)])
    zones = models.JSONField(default=list, blank=True)
    services = models.JSONField(default=list, blank=True)
    accessibility = models.TextField(blank=True)
    evaluation = models.JSONField(default=dict, blank=True)


class Category(Record):
    code = models.CharField(max_length=30, unique=True)
    name = models.CharField(max_length=100)
    parent = models.ForeignKey('self', null=True, blank=True, on_delete=models.PROTECT)


class Book(Record):
    isbn = models.CharField(max_length=20, unique=True)
    title = models.CharField(max_length=200, db_index=True)
    author = models.CharField(max_length=150, db_index=True)
    publisher = models.CharField(max_length=150, blank=True)
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name='books')
    call_number = models.CharField(max_length=50)
    price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    cover = models.URLField(blank=True)
    active = models.BooleanField(default=True)


class Copy(Record):
    class Status(models.TextChoices):
        AVAILABLE = 'available', '在馆'
        LOANED = 'loaned', '借出'
        RESERVED = 'reserved', '预约'
        PROCESSING = 'processing', '待处理'
        TRANSIT = 'transit', '在途'
        WITHDRAWN = 'withdrawn', '下架'
        LOST = 'lost', '遗失'
    book = models.ForeignKey(Book, on_delete=models.PROTECT, related_name='copies')
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name='copies')
    rfid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    shelf = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.AVAILABLE, db_index=True)
    disinfected_at = models.DateTimeField(null=True, blank=True)
    shelving_due_at = models.DateTimeField(null=True, blank=True)


class Rule(Record):
    name = models.CharField(max_length=20, unique=True, default='default')
    loan_limit = models.PositiveIntegerField(default=5, validators=[MinValueValidator(1)])
    verified_loan_limit = models.PositiveIntegerField(default=10, validators=[MinValueValidator(1)])
    loan_days = models.PositiveIntegerField(default=30, validators=[MinValueValidator(1)])
    verified_loan_days = models.PositiveIntegerField(default=45, validators=[MinValueValidator(1)])
    renewal_limit = models.PositiveIntegerField(default=1)
    reservation_limit = models.PositiveIntegerField(default=5, validators=[MinValueValidator(1)])
    hold_days = models.PositiveIntegerField(default=2, validators=[MinValueValidator(1)])
    fine_per_day = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal('0.50'), validators=[MinValueValidator(0)])
    minimum_credit = models.PositiveIntegerField(default=60, validators=[MaxValueValidator(200)])
    reservation_deposit = models.DecimalField(max_digits=10, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    disinfection_required = models.BooleanField(default=True)
    shelving_hours = models.PositiveIntegerField(default=24, validators=[MinValueValidator(1)])
    offline_minutes = models.PositiveIntegerField(default=5, validators=[MinValueValidator(1)])
    response_hours = models.PositiveIntegerField(default=24, validators=[MinValueValidator(1)])
    retention_days = models.PositiveIntegerField(default=180, validators=[MinValueValidator(1)])
    financial_retention_days = models.PositiveIntegerField(default=1825, validators=[MinValueValidator(1)])
    holidays = models.JSONField(default=list, blank=True)


class Loan(Record):
    reader = models.ForeignKey(User, on_delete=models.PROTECT, related_name='loans')
    copy = models.ForeignKey(Copy, on_delete=models.PROTECT, related_name='loans')
    borrowed_at = models.DateTimeField()
    due_at = models.DateTimeField(db_index=True)
    returned_at = models.DateTimeField(null=True, blank=True)
    renewals = models.PositiveIntegerField(default=0)
    # Portable to MySQL: a nullable unique key enforces one live loan per copy.
    active_copy = models.OneToOneField(Copy, null=True, blank=True, on_delete=models.PROTECT, related_name='+')

    class Meta(Record.Meta):
        indexes = [models.Index(fields=['reader', 'returned_at'], name='loan_reader_returned_idx')]


class Reservation(Record):
    reader = models.ForeignKey(User, on_delete=models.PROTECT)
    book = models.ForeignKey(Book, on_delete=models.PROTECT, related_name='reservations')
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT)
    copy = models.ForeignKey(Copy, null=True, blank=True, on_delete=models.PROTECT)
    status = models.CharField(max_length=20, default='waiting', choices=[(v, v) for v in ['waiting', 'ready', 'collected', 'cancelled', 'expired']])
    expires_at = models.DateTimeField(null=True, blank=True)


class Fine(Record):
    loan = models.OneToOneField(Loan, on_delete=models.PROTECT)
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    paid_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    assessed_days = models.PositiveIntegerField(default=0)


class Payment(Record):
    reference = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    reader = models.ForeignKey(User, on_delete=models.PROTECT)
    fine = models.ForeignKey(Fine, on_delete=models.PROTECT)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, default='pending', choices=[('pending', 'pending'), ('paid', 'paid')])
    paid_at = models.DateTimeField(null=True, blank=True)


class CreditEntry(Record):
    reader = models.ForeignKey(User, on_delete=models.PROTECT)
    delta = models.IntegerField()
    balance = models.PositiveIntegerField()
    reason = models.CharField(max_length=255)


class DepositEntry(Record):
    reader = models.ForeignKey(User, on_delete=models.PROTECT)
    delta = models.DecimalField(max_digits=10, decimal_places=2)
    balance = models.DecimalField(max_digits=10, decimal_places=2)
    reason = models.CharField(max_length=255)


class Notification(Record):
    reader = models.ForeignKey(User, on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    body = models.TextField()
    read_at = models.DateTimeField(null=True, blank=True)
    deduplication_key = models.CharField(max_length=100, null=True, unique=True)


class Announcement(Record):
    title = models.CharField(max_length=200)
    body = models.TextField()
    published = models.BooleanField(default=True)


class Consent(Record):
    reader = models.ForeignKey(User, on_delete=models.CASCADE)
    purpose = models.CharField(max_length=30, choices=[('biometric', '生物识别'), ('identity', '实名核验')])
    policy_version = models.CharField(max_length=30)
    granted = models.BooleanField()


class Device(Record):
    name = models.CharField(max_length=100)
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT)
    kind = models.CharField(max_length=20, choices=[(v, v) for v in ['rfid', 'gate', 'camera', 'sensor', 'smoke', 'terminal', 'light', 'ac']])
    online = models.BooleanField(default=False)
    last_seen = models.DateTimeField(null=True, blank=True)
    shadow = models.JSONField(default=dict, blank=True)


class DeviceEvent(Record):
    event_id = models.UUIDField(unique=True)
    device = models.ForeignKey(Device, on_delete=models.PROTECT)
    kind = models.CharField(max_length=30)
    payload = models.JSONField(default=dict)


class DeviceCommand(Record):
    device = models.ForeignKey(Device, on_delete=models.PROTECT)
    actor = models.ForeignKey(User, null=True, on_delete=models.PROTECT)
    command = models.CharField(max_length=30)
    reason = models.CharField(max_length=255)
    status = models.CharField(max_length=20, default='pending')
    signature = models.CharField(max_length=64, blank=True)


class Alert(Record):
    device = models.ForeignKey(Device, null=True, blank=True, on_delete=models.PROTECT)
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT)
    severity = models.CharField(max_length=20, choices=[(v, v) for v in ['info', 'warning', 'critical']])
    kind = models.CharField(max_length=30)
    message = models.TextField()
    status = models.CharField(max_length=20, default='open', choices=[(v, v) for v in ['open', 'acknowledged', 'resolved']])
    resolution = models.TextField(blank=True)


class Visit(Record):
    reader = models.ForeignKey(User, on_delete=models.PROTECT)
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT)
    entered_at = models.DateTimeField()
    exited_at = models.DateTimeField(null=True, blank=True)
    active_reader = models.OneToOneField(User, null=True, blank=True, on_delete=models.PROTECT, related_name='+')

    class Meta(Record.Meta):
        indexes = [models.Index(fields=['branch', 'entered_at'], name='visit_branch_entered_idx')]


class Transfer(Record):
    copy = models.ForeignKey(Copy, on_delete=models.PROTECT)
    source = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name='+')
    destination = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name='+')
    route = models.CharField(max_length=255)
    schedule = models.DateTimeField()
    status = models.CharField(max_length=20, default='planned', choices=[(v, v) for v in ['planned', 'shipped', 'received', 'cancelled']])
    notes = models.TextField(blank=True)


class WorkOrder(Record):
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT)
    device = models.ForeignKey(Device, null=True, blank=True, on_delete=models.PROTECT)
    assignee = models.ForeignKey(User, null=True, blank=True, on_delete=models.PROTECT)
    kind = models.CharField(max_length=30, choices=[(v, v) for v in ['technical', 'books', 'hygiene', 'safety']])
    title = models.CharField(max_length=200)
    status = models.CharField(max_length=20, default='open', choices=[(v, v) for v in ['open', 'in_progress', 'completed', 'reviewed']])
    due_at = models.DateTimeField()
    result = models.TextField(blank=True)
    review = models.TextField(blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)


class Inventory(Record):
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT)
    shelf = models.CharField(max_length=100, blank=True)
    observed = models.JSONField(default=list)
    report = models.JSONField(default=dict)


class OperationRecord(Record):
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT)
    kind = models.CharField(max_length=30, choices=[(v, v) for v in ['responsibility', 'performance', 'labor', 'cost', 'emergency_plan', 'drill', 'video']])
    title = models.CharField(max_length=200)
    details = models.JSONField(default=dict, blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    hours = models.DecimalField(max_digits=10, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    occurred_on = models.DateField()
    expires_at = models.DateTimeField(null=True, blank=True)


class Activity(Record):
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT)
    title = models.CharField(max_length=200)
    audience = models.CharField(max_length=100)
    starts_at = models.DateTimeField()
    capacity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    published = models.BooleanField(default=True)


class Enrollment(Record):
    activity = models.ForeignKey(Activity, on_delete=models.CASCADE, related_name='enrollments')
    reader = models.ForeignKey(User, on_delete=models.CASCADE)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['activity', 'reader'], name='one_enrollment')]


class AuditLog(Record):
    actor = models.ForeignKey(User, null=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=100)
    resource = models.CharField(max_length=100)
    details = models.JSONField(default=dict)


class Idempotency(Record):
    actor = models.ForeignKey(User, on_delete=models.CASCADE)
    key = models.CharField(max_length=128)
    operation = models.CharField(max_length=100)
    digest = models.CharField(max_length=64)
    response = models.JSONField(default=dict)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['actor', 'key'], name='unique_idempotency_key')]


class DomainEvent(Record):
    event_id = models.UUIDField(default=uuid.uuid4, unique=True)
    kind = models.CharField(max_length=60)
    payload = models.JSONField(default=dict)
    published_at = models.DateTimeField(null=True, blank=True)


class OfflineReceipt(Record):
    event_id = models.UUIDField(unique=True)
    uploaded_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL)
    digest = models.CharField(max_length=64)
    response = models.JSONField(default=dict)


class MqttInbox(Record):
    digest = models.CharField(max_length=64, unique=True)
    topic = models.CharField(max_length=512)
    payload = models.BinaryField()
    status = models.CharField(max_length=16, default='pending', db_index=True,
        choices=[('pending', '待处理'), ('processed', '已处理'), ('rejected', '无效消息')])
    error = models.TextField(blank=True)
