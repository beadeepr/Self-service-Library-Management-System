from django.conf import settings
from django.core.cache import cache
from django.db import connection
from drf_spectacular.utils import extend_schema, OpenApiTypes
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


@extend_schema(responses=OpenApiTypes.OBJECT)
@api_view(['GET'])
@permission_classes([AllowAny])
def readiness(request):
    checks = {}
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
            checks['database'] = cursor.fetchone()[0] == 1
    except Exception:
        checks['database'] = False
    try:
        cache.set('health:probe', 'ok', 10)
        checks['cache'] = cache.get('health:probe') == 'ok'
    except Exception:
        checks['cache'] = False
    ready = all(checks.values())
    return Response({'status': 'ready' if ready else 'unavailable', 'checks': checks,
        'cache_mode': 'redis' if settings.REDIS_URL else 'local'}, status=200 if ready else 503)
