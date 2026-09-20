import base64
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESSIV
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from django.conf import settings
from django.db import models


class EncryptedCharField(models.CharField):
    """AES-SIV authenticated encryption with exact lookup support.

    Deterministic ciphertext exposes equality, not plaintext. Substring lookups
    are intentionally unsupported; keep encryption keys outside the database.
    """
    prefix = 'siv1:'

    def _cipher(self):
        key = HKDF(algorithm=hashes.SHA256(), length=64, salt=b'library-field-v1',
            info=b'authenticated-storage').derive(settings.FIELD_ENCRYPTION_KEY.encode())
        return AESSIV(key)

    def _context(self):
        return [f'{self.model._meta.label_lower}.{self.name}'.encode()]

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        if value is None:
            return None
        encrypted = self._cipher().encrypt(value.encode(), self._context())
        return self.prefix+base64.urlsafe_b64encode(encrypted).decode()

    def from_db_value(self, value, expression, connection):
        if value is None or not value.startswith(self.prefix):
            # Allows migration of existing plaintext rows via an explicit re-save.
            return value
        encrypted = base64.urlsafe_b64decode(value[len(self.prefix):])
        return self._cipher().decrypt(encrypted, self._context()).decode()

    def db_type(self, connection):
        # API/form max_length applies to plaintext, DB column accommodates UTF-8 + tag.
        return f'varchar({max(256, ((self.max_length * 4 + 18) // 3) * 4 + 5)})'

    def get_lookup(self, lookup_name):
        if lookup_name not in ['exact', 'in', 'isnull']:
            return None
        return super().get_lookup(lookup_name)
