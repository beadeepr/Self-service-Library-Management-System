from datetime import timedelta
from decimal import Decimal
from math import ceil
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from django.shortcuts import get_object_or_404
from library.models import (Book, Copy, CreditEntry, Fine, Loan, Notification, Reservation, User)
from .common import audit, owner_or_admin, require, rules, StockUnavailable
from library.events import emit


def shift_holidays(value, rule):
    while value.date().isoformat() in rule.holidays:
        value += timedelta(days=1)
    return value


def eligible(reader, rule):
    require(reader.is_active and not reader.frozen, '读者账号已冻结或失效，请联系管理员')
    require(reader.credit >= rule.minimum_credit, '信用不足，暂不可借阅')
    require(not Loan.objects.filter(reader=reader, returned_at=None, due_at__lt=timezone.now()).exists(), '有逾期图书，请先归还')
    require(not Fine.objects.filter(loan__reader=reader, amount__gt=F('paid_amount')).exists(), '有未缴清罚款')


def change_credit(reader, delta, reason):
    before = reader.credit
    reader.credit = max(0, min(200, before + delta))
    reader.save(update_fields=['credit'])
    CreditEntry.objects.create(reader=reader, delta=reader.credit - before, balance=reader.credit, reason=reason)


def notify(reader, title, body, key=None):
    if key:
        return Notification.objects.get_or_create(deduplication_key=key,
            defaults={'reader': reader, 'title': title, 'body': body})[0]
    return Notification.objects.create(reader=reader, title=title, body=body)


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


def assign_hold(copy):
    reservation = Reservation.objects.select_for_update().filter(
        book=copy.book, branch=copy.branch, status='waiting').order_by('created_at', 'id').first()
    if reservation:
        reservation.status = 'ready'
        reservation.copy = copy
        reservation.expires_at = timezone.now() + timedelta(days=rules().hold_days)
        reservation.save()
        copy.status = 'reserved'
        notify(reservation.reader, '预约图书到馆', f'《{copy.book.title}》已到馆，请在保留期内取书。')
    else:
        copy.status = 'available'
    copy.save()


@transaction.atomic
def borrow(actor, reader_id, copy_id, occurred_at=None):
    owner_or_admin(actor, reader_id)
    reader = get_object_or_404(User.objects.select_for_update(), pk=reader_id)
    book_id = get_object_or_404(Copy, pk=copy_id).book_id
    Book.objects.select_for_update().get(pk=book_id)
    copy = get_object_or_404(Copy.objects.select_for_update(), pk=copy_id)
    rule = rules()
    eligible(reader, rule)
    limit = rule.verified_loan_limit if reader.verified else rule.loan_limit
    require(Loan.objects.filter(reader=reader, returned_at=None).count() < limit, '已达到借阅上限')
    require(copy.book.active and copy.branch.active, '图书已下架或网点停用')
    if copy.status not in ['available', 'reserved']:
        raise StockUnavailable()
    hold = None
    if copy.status == 'reserved':
        hold = Reservation.objects.select_for_update().filter(copy=copy, status='ready').first()
        require(hold and hold.reader_id == reader.pk and hold.expires_at > timezone.now(), '图书已为其他读者保留或预约已过期')
    now = occurred_at or timezone.now()
    days = rule.verified_loan_days if reader.verified else rule.loan_days
    loan = Loan.objects.create(reader=reader, copy=copy, active_copy=copy, borrowed_at=now,
        due_at=shift_holidays(now + timedelta(days=days), rule))
    copy.status = 'loaned'
    copy.save()
    if hold:
        hold.status = 'collected'
        hold.save()
    audit(actor, 'loan.borrow', loan)
    emit('loan.borrowed', loan=loan.pk, copy=copy.pk, branch=copy.branch_id)
    notify(reader, '借阅成功', f'《{copy.book.title}》应于 {loan.due_at.isoformat()} 归还')
    return {'id': loan.pk, 'copy': copy.pk, 'due_at': loan.due_at.isoformat()}


@transaction.atomic
def return_book(actor, loan_id, branch_id, damaged=False, occurred_at=None):
    snapshot = get_object_or_404(Loan, pk=loan_id)
    owner_or_admin(actor, snapshot.reader_id)
    User.objects.select_for_update().get(pk=snapshot.reader_id)
    Book.objects.select_for_update().get(pk=snapshot.copy.book_id)
    copy = Copy.objects.select_for_update().get(pk=snapshot.copy_id)
    loan = Loan.objects.select_for_update().get(pk=loan_id)
    require(loan.returned_at is None, '图书已归还')
    from library.models import Branch
    branch = get_object_or_404(Branch, pk=branch_id, active=True)
    loan.returned_at = occurred_at or timezone.now()
    require(loan.returned_at >= loan.borrowed_at, '归还时间不能早于借出时间')
    if occurred_at:
        prior_fine = Fine.objects.filter(loan=loan).first()
        event_days = max(0, ceil((occurred_at-loan.due_at).total_seconds()/86400))
        require(not prior_fine or prior_fine.assessed_days <= event_days,
                '离线归还时间早于已计费日期，请管理员复核罚款后补录')
    loan.active_copy = None
    loan.save()
    fine = assess_fine(loan)
    copy.branch = branch
    copy.disinfected_at = None
    copy.shelving_due_at = timezone.now() + timedelta(hours=rules().shelving_hours)
    copy.status = 'processing'
    copy.save()
    if damaged:
        reader = User.objects.select_for_update().get(pk=loan.reader_id)
        change_credit(reader, -10, f'归还图书损坏：{copy.pk}')
    elif not rules().disinfection_required:
        assign_hold(copy)
    audit(actor, 'loan.return', loan, damaged=damaged, branch=branch_id)
    emit('loan.returned', loan=loan.pk, copy=copy.pk, branch=branch_id)
    notify(loan.reader, '归还成功', f'《{copy.book.title}》已归还，处理状态：{copy.status}')
    return {'id': loan.pk, 'copy_status': copy.status, 'fine': str(fine.amount) if fine else '0.00'}


@transaction.atomic
def renew(actor, loan_id):
    snapshot = get_object_or_404(Loan, pk=loan_id)
    owner_or_admin(actor, snapshot.reader_id)
    reader = User.objects.select_for_update().get(pk=snapshot.reader_id)
    Book.objects.select_for_update().get(pk=snapshot.copy.book_id)
    loan = Loan.objects.select_for_update().get(pk=loan_id)
    rule = rules()
    eligible(reader, rule)
    require(loan.returned_at is None and loan.due_at > timezone.now(), '已归还或逾期图书不可续借')
    require(loan.renewals < rule.renewal_limit, '续借次数已达上限')
    require(not Reservation.objects.filter(book=loan.copy.book, status__in=['waiting', 'ready']).exists(), '已有读者预约，不可续借')
    days = rule.verified_loan_days if reader.verified else rule.loan_days
    loan.due_at = shift_holidays(loan.due_at + timedelta(days=days), rule)
    loan.renewals += 1
    loan.save()
    audit(actor, 'loan.renew', loan)
    return {'id': loan.pk, 'due_at': loan.due_at.isoformat(), 'renewals': loan.renewals}


@transaction.atomic
def reserve(actor, book_id, branch_id):
    reader = User.objects.select_for_update().get(pk=actor.pk)
    book = get_object_or_404(Book.objects.select_for_update(), pk=book_id, active=True)
    rule = rules()
    eligible(reader, rule)
    require(reader.deposit >= rule.reservation_deposit, '押金不足，请联系管理员处理')
    from library.models import Branch
    get_object_or_404(Branch, pk=branch_id, active=True)
    copies = Copy.objects.filter(book=book, branch_id=branch_id)
    require(copies.filter(status='loaned').exists() and not copies.filter(status='available').exists(), '仅可预约已有借出馆藏且无可借副本的图书')
    active = Reservation.objects.filter(reader=reader, status__in=['waiting', 'ready'])
    require(active.count() < rule.reservation_limit, '已达到预约上限')
    require(not active.filter(book=book).exists(), '不可重复预约同一图书')
    reservation = Reservation.objects.create(reader=reader, book=book, branch_id=branch_id)
    audit(actor, 'reservation.create', reservation)
    return {'id': reservation.pk, 'status': reservation.status}


@transaction.atomic
def cancel_reservation(actor, pk):
    snapshot = get_object_or_404(Reservation, pk=pk)
    owner_or_admin(actor, snapshot.reader_id)
    Book.objects.select_for_update().get(pk=snapshot.book_id)
    reservation = Reservation.objects.select_for_update().get(pk=pk)
    require(reservation.status in ['waiting', 'ready'], '当前状态不可取消')
    reservation.status = 'cancelled'
    reservation.save()
    if reservation.copy_id:
        assign_hold(Copy.objects.select_for_update().get(pk=reservation.copy_id))
    audit(actor, 'reservation.cancel', reservation)
    return {'id': pk, 'status': 'cancelled'}


@transaction.atomic
def shelve(actor, copy_id, shelf):
    snapshot = get_object_or_404(Copy, pk=copy_id)
    Book.objects.select_for_update().get(pk=snapshot.book_id)
    copy = Copy.objects.select_for_update().get(pk=copy_id)
    require(copy.status == 'processing', '仅待处理图书可上架')
    require(not rules().disinfection_required or copy.disinfected_at, '请先完成消毒登记')
    copy.shelf = shelf
    assign_hold(copy)
    audit(actor, 'copy.shelve', copy)
    return {'id': copy.pk, 'status': copy.status}
