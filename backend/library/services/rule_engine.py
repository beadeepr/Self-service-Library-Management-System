from datetime import timedelta
from django.db.models import F
from django.utils import timezone
from library.models import Fine, Loan
from .common import require


def shift_holidays(value, rule):
    while timezone.localdate(value).isoformat() in rule.holidays:
        value += timedelta(days=1)
    return value


def eligible(reader, rule):
    require(reader.is_active and not reader.frozen, '读者账号已冻结或失效，请联系管理员')
    require(reader.credit >= rule.minimum_credit, '信用不足，暂不可借阅')
    require(not Loan.objects.filter(reader=reader, returned_at=None, due_at__lt=timezone.now()).exists(), '有逾期图书，请先归还')
    require(not Fine.objects.filter(loan__reader=reader, amount__gt=F('paid_amount')).exists(), '有未缴清罚款')
