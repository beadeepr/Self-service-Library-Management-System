from library.models import DomainEvent


def emit(kind, **payload):
    """Transactional outbox: persist beside the business write, publish after commit."""
    return DomainEvent.objects.create(kind=kind, payload=payload)
