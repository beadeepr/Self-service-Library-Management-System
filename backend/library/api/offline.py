from django.http import Http404
from django.utils import timezone
from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from library.services import circulation_service as circulation
from library.services.common import audit, is_admin, offline_idempotent, require
from . import serializers as s
from .auth import validated


class OfflineViewSet(viewsets.GenericViewSet):
    serializer_class = s.OfflineBatchSerializer
    # 终端以读者身份运行，补传必须允许读者提交自己的交易；服务层仍会校验归属与资格。
    permission_classes = [permissions.IsAuthenticated]

    @action(detail=False, methods=['post'])
    def sync(self, request):
        data = validated(s.OfflineBatchSerializer, request)
        results = []
        for item in data['transactions']:
            try:
                def execute():
                    require(item['occurred_at'] <= timezone.now(), '离线交易时间不能在未来')
                    if item['kind'] == 'borrow':
                        # 读者身份的终端可以省略 reader，默认就是本人；管理员代传时仍须显式指定。
                        reader_id = item.get('reader')
                        if reader_id is None and not is_admin(request.user):
                            reader_id = request.user.pk
                        require(reader_id is not None and 'copy' in item, '借书需要 reader、copy')
                        result = circulation.borrow(request.user, reader_id, item['copy'], occurred_at=item['occurred_at'])
                    else:
                        require('loan' in item and 'branch' in item, '还书需要 loan、branch')
                        result = circulation.return_book(request.user, item['loan'], item['branch'],
                            damaged=item.get('damaged', False), occurred_at=item['occurred_at'],
                            allow_other_reader=True)
                    audit(request.user, 'offline.reconcile', request.user, event_id=str(item['event_id']), occurred_at=item['occurred_at'].isoformat())
                    return result
                result = offline_idempotent(request.user, item['event_id'], item, execute)
                results.append({'event_id': item['event_id'], 'status': 'applied', 'result': result})
            except (APIException, Http404) as exc:
                results.append({'event_id': item['event_id'], 'status': 'conflict', 'detail': getattr(exc, 'detail', str(exc))})
        return Response({'results': results})
