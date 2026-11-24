"""PaymentsProvider interface + webhook signing (D8, NFR-3).

Flow (same for mock and a real vendor):
  1. After APPROVE, the app moves the run to PROCESSING and calls submit_payout(...) with the run's
     idempotency_key. Calling again with the same key returns the same payout (no double pay).
  2. Later the provider POSTs to /api/webhooks/payments with a signed event.
  3. The webhook handler is the ONLY code that moves PROCESSING -> PAID / FAILED.

Webhook wire format (JSON body), header `X-Forte-Signature: <hex hmac-sha256(secret, raw body)>`:
  {"event_id": "evt_...", "type": "payout.paid" | "payout.failed",
   "payout_id": "po_...", "idempotency_key": "<uuid>", "run_id": "<uuid>",
   "failure_reason": null | "..."}
"""

import hashlib
import hmac
import uuid
from dataclasses import dataclass
from datetime import date
from typing import Literal, Protocol

SIGNATURE_HEADER = "X-Forte-Signature"


@dataclass(frozen=True)
class PayoutLine:
    employee_id: uuid.UUID
    bank_account_id: uuid.UUID | None
    net_cents: int


@dataclass(frozen=True)
class PayoutRequest:
    run_id: uuid.UUID
    company_id: uuid.UUID
    idempotency_key: uuid.UUID
    pay_date: date
    total_net_cents: int
    lines: list[PayoutLine]


@dataclass(frozen=True)
class PayoutReceipt:
    provider_payout_id: str
    status: Literal["pending", "paid", "failed"]


class PaymentsProviderError(Exception):
    """Provider unavailable. The run stays APPROVED and the Admin can retry (NFR-14)."""


class PaymentsProvider(Protocol):
    def submit_payout(self, request: PayoutRequest) -> PayoutReceipt: ...


def sign(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def verify_signature(secret: str, body: bytes, signature: str | None) -> bool:
    return bool(signature) and hmac.compare_digest(sign(secret, body), signature or "")
