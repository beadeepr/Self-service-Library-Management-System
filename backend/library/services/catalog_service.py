from django.db import transaction
from django.shortcuts import get_object_or_404
from library.models import Book, Copy
from .common import audit, require, rules


@transaction.atomic
def shelve(actor, copy_id, shelf):
    from .circulation_service import assign_hold
    snapshot = get_object_or_404(Copy, pk=copy_id)
    Book.objects.select_for_update().get(pk=snapshot.book_id)
    copy = Copy.objects.select_for_update().get(pk=copy_id)
    require(copy.status == 'processing', '仅待处理图书可上架')
    require(not rules().disinfection_required or copy.disinfected_at, '请先完成消毒登记')
    copy.shelf = shelf
    assign_hold(copy)
    audit(actor, 'copy.shelve', copy)
    return {'id': copy.pk, 'status': copy.status}
