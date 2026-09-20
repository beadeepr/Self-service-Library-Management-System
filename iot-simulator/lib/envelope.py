import uuid


def event_envelope(kind: str, payload: dict | None = None) -> dict:
    """与 backend/library/adapters.py 的 event_envelope 格式一致。"""
    return {
        'event_id': str(uuid.uuid4()),
        'kind': kind,
        'payload': payload or {},
    }
