from django.http import Http404
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from library.services import circulation_service as circulation
from library.services.common import audit, offline_idempotent, require
from . import serializers as s
from .auth import validated
from .common import AdminOnly


class OfflineViewSet(viewsets.GenericViewSet):
    serializer_class = s.OfflineBatchSerializer
    permission_classes = [AdminOnly]

    @action(detail=False, methods=['post'])
    def sync(self, request):
        data = validated(s.OfflineBatchSerializer, request)
        results = []
        for item in data['transactions']:
            try:
                def execute():
                    require(item['occurred_at'] <= timezone.now(), '离线交易时间不能在未来')
                    if item['kind'] == 'borrow':
                        require('reader' in item and 'copy' in item, '借书需要 reader、copy')
                        result = circulation.borrow(request.user, item['reader'], item['copy'], occurred_at=item['occurred_at'])
                    else:
                        require('loan' in item and 'branch' in item, '还书需要 loan、branch')
                        result = circulation.return_book(request.user, item['loan'], item['branch'], occurred_at=item['occurred_at'])
                    audit(request.user, 'offline.reconcile', request.user, event_id=str(item['event_id']), occurred_at=item['occurred_at'].isoformat())
                    return result
                result = offline_idempotent(request.user, item['event_id'], item, execute)
                results.append({'event_id': item['event_id'], 'status': 'applied', 'result': result})
            except (APIException, Http404) as exc:
                results.append({'event_id': item['event_id'], 'status': 'conflict', 'detail': getattr(exc, 'detail', str(exc))})
        return Response({'results': results})
