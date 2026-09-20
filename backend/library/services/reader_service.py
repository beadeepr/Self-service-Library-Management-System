from django.conf import settings
from django.utils.crypto import salted_hmac
from library.models import Consent
from django.db import transaction
from library.models import CreditEntry, User
from .common import audit, require


def change_credit(reader, delta, reason):
    before = reader.credit
    reader.credit = max(0, min(200, before + delta))
    reader.save(update_fields=['credit'])
    CreditEntry.objects.create(reader=reader, delta=reader.credit - before, balance=reader.credit, reason=reason)


@transaction.atomic
def verify_identity(actor, identity):
    require(settings.SIMULATION_ENABLED, '实名认证供应商尚未配置')
    consent = Consent.objects.filter(reader=actor, purpose='identity').order_by('-id').first()
    require(consent and consent.granted, '请先同意实名认证告知')
    user = User.objects.select_for_update().get(pk=actor.pk)
    digest = salted_hmac('identity', identity, algorithm='sha256').hexdigest()
    require(not User.objects.filter(identity_digest=digest).exclude(pk=user.pk).exists(), '此证件已绑定其他账号')
    user.identity_digest = digest
    user.verified = True
    user.save(update_fields=['identity_digest', 'verified'])
    audit(actor, 'identity.verify.simulated', user)
    return {'verified': True, 'simulation': True}
