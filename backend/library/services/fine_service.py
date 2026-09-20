import hashlib
import hmac
import time
from django.conf import settings
from library.models import Payment
from decimal import Decimal
from math import ceil
from django.db import transaction
from django.utils import timezone
from django.shortcuts import get_object_or_404
from library.models import Fine, User
from .common import audit, owner_or_admin, require, rules
from .reader_service import change_credit


def assess_fine(loan, at=None):
    at = at or loan.returned_at or timezone.now()
    overdue_seconds = (at - loan.due_at).total_seconds()
    days = max(0, ceil(overdue_seconds / 86400))
    if not days:
        return None
    fine, _ = Fine.objects.select_for_update().get_or_create(loan=loan)
    if days > fine.assessed_days:
        delta = days - fine.assessed_days
        fine.amount += rules().fine_per_day * delta
        fine.assessed_days = days
        fine.save()
        reader = User.objects.select_for_update().get(pk=loan.reader_id)
        change_credit(reader, -delta, f'借阅 {loan.pk} 逾期新增 {delta} 天')
    return fine


@transaction.atomic
def create_payment(actor, fine_id):
    fine = get_object_or_404(Fine.objects.select_for_update(), pk=fine_id)
    owner_or_admin(actor, fine.loan.reader_id)
    amount = fine.amount - fine.paid_amount
    require(amount > 0, '罚款已缴清')
    payment = Payment.objects.filter(fine=fine, status='pending', amount=amount).first()
    if not payment:
        payment = Payment.objects.create(reader=fine.loan.reader, fine=fine, amount=amount)
    audit(actor, 'payment.create', payment)
    return {'id': payment.pk, 'reference': str(payment.reference), 'amount': str(payment.amount), 'status': payment.status}


@transaction.atomic
def settle(payment_id, actor=None):
    snapshot = get_object_or_404(Payment, pk=payment_id)
    User.objects.select_for_update().get(pk=snapshot.reader_id)
    fine = Fine.objects.select_for_update().get(pk=snapshot.fine_id)
    payment = Payment.objects.select_for_update().get(pk=payment_id)
    if payment.status == 'paid':
        return {'id': payment.pk, 'status': 'paid'}
    require(payment.amount <= fine.amount - fine.paid_amount, '订单已过期，请重新创建缴费订单')
    fine.paid_amount += payment.amount
    fine.save()
    payment.status = 'paid'
    payment.paid_at = timezone.now()
    payment.save()
    audit(actor, 'payment.settle', payment)
    return {'id': payment.pk, 'status': 'paid'}


def signature(reference, amount, timestamp):
    message = f'{reference}|{amount}|{timestamp}'
    return hmac.new(settings.PAYMENT_SIGNING_KEY.encode(), message.encode(), hashlib.sha256).hexdigest()


def callback(reference, amount, timestamp, supplied_signature):
    require(abs(time.time() - timestamp) <= 300, '回调已过期')
    require(hmac.compare_digest(signature(reference, amount, timestamp), supplied_signature), '支付签名错误')
    payment = get_object_or_404(Payment, reference=reference)
    require(payment.amount == Decimal(amount), '支付金额不匹配')
    return settle(payment.pk)
