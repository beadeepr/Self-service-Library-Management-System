import uuid
from rest_framework.renderers import JSONRenderer


class EnvelopeJSONRenderer(JSONRenderer):
    def render(self, data, accepted_media_type=None, renderer_context=None):
        context = renderer_context or {}
        response = context.get('response')
        status = response.status_code if response else 200
        request = context.get('request')
        request_id = getattr(request, 'request_id', None) or str(uuid.uuid4())
        code = getattr(response, 'business_code', 0 if status < 400 else status * 100)
        message = 'ok'
        if code:
            detail = data.get('detail') if isinstance(data, dict) else None
            message = str(detail) if detail else '请求未完成，请检查 data 中的错误详情'
        if response:
            response['X-Request-ID'] = request_id
        return super().render({'code': code, 'message': message, 'data': data, 'request_id': request_id}, accepted_media_type, context)


def envelope_schema(result, generator, request, public):
    for path, operations in result.get('paths', {}).items():
        if not path.startswith('/api/v1/'):
            continue
        for operation in operations.values():
            if not isinstance(operation, dict):
                continue
            for status, response in operation.get('responses', {}).items():
                content = response.get('content', {}).get('application/json')
                if not content:
                    continue
                payload = content.get('schema', {})
                content['schema'] = {'type': 'object', 'required': ['code', 'message', 'data', 'request_id'],
                    'properties': {'code': {'type': 'integer', 'description': '0 为成功；4001 为库存不可借；HTTP 错误使用状态码 × 100'},
                        'message': {'type': 'string'}, 'data': payload,
                        'request_id': {'type': 'string', 'format': 'uuid'}}}
    return result
