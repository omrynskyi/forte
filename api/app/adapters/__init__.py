"""Adapter factories, used as FastAPI dependencies so tests can override them:

app.dependency_overrides[get_tax_provider] = lambda: FakeTax()
"""

from functools import lru_cache

from app.adapters.bank import BankVerifier
from app.adapters.email import ConsoleEmailSender, EmailSender, SmtpEmailSender
from app.adapters.mock.bank import MockBankVerifier
from app.adapters.mock.payments import MockPaymentsProvider
from app.adapters.mock.tax import MockTaxProvider
from app.adapters.payments import PaymentsProvider
from app.adapters.storage import MemoryStorage, S3Storage, StorageAdapter
from app.adapters.tax import TaxProvider
from app.config import get_settings


def get_tax_provider() -> TaxProvider:
    return MockTaxProvider()


def get_payments_provider() -> PaymentsProvider:
    return MockPaymentsProvider()


def get_bank_verifier() -> BankVerifier:
    return MockBankVerifier()


@lru_cache
def get_storage() -> StorageAdapter:
    s = get_settings()
    return MemoryStorage(s.s3_bucket) if s.storage_backend == "memory" else S3Storage(s)


@lru_cache
def get_email_sender() -> EmailSender:
    return SmtpEmailSender() if get_settings().email_sender == "smtp" else ConsoleEmailSender()
