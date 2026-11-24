"""Runtime configuration. Every setting comes from an environment variable prefixed FORTE_.

See `.env.example` at the repo root for the full list with demo-safe defaults.
"""

from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_ENCRYPTION_KEY = "9M4KS6XrbaQX0kvWX_CWIqUPWRDGrJM2VayH8EeIATQ="  # public, fake-data only


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FORTE_", env_file=".env", extra="ignore")

    env: Literal["dev", "test", "demo", "prod"] = "dev"

    database_url: str = "postgresql+psycopg://forte:forte@localhost:5432/forte"

    # Fernet key (urlsafe base64, 32 bytes). Generate: `make key`. This default is a PUBLIC dev-only
    # key so fake data works out of the box; prod must set its own (config refuses the default).
    encryption_key: str = DEV_ENCRYPTION_KEY

    # Where links in emails point (the Next.js app) and where the API can reach itself.
    web_base_url: str = "http://localhost:3000"
    api_base_url: str = "http://localhost:8000"

    # Sessions
    session_cookie_name: str = "forte_session"
    session_cookie_secure: bool = False  # True in prod (HTTPS). False for localhost/LAN demo.
    session_ttl_hours: int = 12
    magic_link_ttl_minutes: int = 15  # AUTH-2

    # Adapters (D5). Only "mock" exists for tax/payments/bank in the MVP.
    tax_provider: Literal["mock"] = "mock"
    payments_provider: Literal["mock"] = "mock"
    bank_verifier: Literal["mock"] = "mock"
    email_sender: Literal["smtp", "console"] = "smtp"

    smtp_host: str = "localhost"
    smtp_port: int = 1025  # Mailpit
    email_from: str = "Forte <no-reply@forte.example>"

    # Payments mock + webhook (D8)
    payments_webhook_secret: str = "dev-webhook-secret"  # noqa: S105 - dev only
    mock_payout_delay_seconds: float = 5.0
    mock_payout_outcome: Literal["paid", "failed"] = "paid"

    # Object storage for paystub PDFs (D16). "s3" = MinIO locally / AWS S3 in prod; "memory" = tests.
    storage_backend: Literal["s3", "memory"] = "s3"
    # Where the API reaches storage. Inside docker compose: http://minio:9000. Empty = AWS default.
    s3_endpoint: str = "http://localhost:9100"
    # Host presigned URLs are SIGNED for: what the browser can reach. Never minio:9000.
    s3_public_endpoint: str = "http://localhost:9100"
    s3_bucket: str = "forte-paystubs"
    s3_region: str = "us-east-1"
    s3_access_key: str = "forte"
    s3_secret_key: str = "forte-dev-secret"  # noqa: S105 - local MinIO only
    paystub_url_ttl_seconds: int = 60  # PAY-3 presigned download lifetime

    # Dev-only "sign in as" switcher (D10). Must be False in prod.
    dev_login_enabled: bool = True

    @property
    def is_prod(self) -> bool:
        return self.env == "prod"

    @model_validator(mode="after")
    def _prod_guardrails(self) -> "Settings":
        if self.env == "prod":
            if self.encryption_key == DEV_ENCRYPTION_KEY:
                raise ValueError("FORTE_ENCRYPTION_KEY must be set to a real key in prod")
            if self.dev_login_enabled:
                raise ValueError("FORTE_DEV_LOGIN_ENABLED must be false in prod")
            if not self.session_cookie_secure:
                raise ValueError("FORTE_SESSION_COOKIE_SECURE must be true in prod")
            if self.storage_backend != "s3":
                raise ValueError("FORTE_STORAGE_BACKEND must be s3 in prod")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
