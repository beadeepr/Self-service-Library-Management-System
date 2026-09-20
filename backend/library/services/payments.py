import hashlib
import hmac
import time
from decimal import Decimal
from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from library.models import Fine, Payment, User
from .common import require, owner_or_admin, audit


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
