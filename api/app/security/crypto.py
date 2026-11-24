"""Field-level encryption for SSN, EIN and bank account numbers (NFR-5, D13).

Use `EncryptedString` as the column type. Store the last 4 digits in a separate plain column for
masked display. Decrypted values only leave the API through the audited "reveal" endpoint (NFR-6).
"""

from functools import lru_cache

from cryptography.fernet import Fernet
from sqlalchemy import String, TypeDecorator

from app.config import get_settings


@lru_cache
def _fernet() -> Fernet:
    return Fernet(get_settings().encryption_key.encode())


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode()


def last4(value: str) -> str:
    digits = "".join(ch for ch in value if ch.isdigit())
    return digits[-4:]


class EncryptedString(TypeDecorator[str]):
    """Transparently encrypts on write and decrypts on read."""

    impl = String
    cache_ok = True

    def process_bind_param(self, value: str | None, dialect) -> str | None:  # noqa: ANN001
        return None if value is None else encrypt(value)

    def process_result_value(self, value: str | None, dialect) -> str | None:  # noqa: ANN001
        return None if value is None else decrypt(value)
