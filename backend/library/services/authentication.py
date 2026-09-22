"""Compatibility imports; maintain authentication in auth_service.py."""
from .auth_service import validate_secret, tokens, issue_code, consume_code, password_login, verify_identity
