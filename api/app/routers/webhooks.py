"""Payments webhook (D8). Task A-05. The ONLY code path that sets PAID or FAILED.

1. Read the raw body; verify X-Forte-Signature with settings.payments_webhook_secret
   (app.adapters.payments.verify_signature). Bad/missing -> 401.
2. Insert WebhookEvent(provider="mock", event_id). Duplicate event_id -> 200 {"status":"duplicate"}
   and do nothing else (replay safety).
3. Find the run by run_id AND idempotency_key. transition(MARK_PAID | MARK_FAILED, actor=None).
4. On PAID: create one Paystub per item (issued_at=now). FINAL runs: flip the employee's membership
   to FORMER. Commit.
5. AFTER the commit, render + store PDFs: app.paystubs.pdf_store.store_pdfs_for_run(run_id) (A-13).
   A storage failure must NOT undo PAID (money already moved); it leaves pdf_object_key NULL and is
   retried by `make paystub-pdfs` (A-13).
No auth cookie: this endpoint is called by the provider, not a browser.
"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.db import get_db
from app.errors import todo

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


@router.post("/payments")
async def payments_webhook(request: Request, db: Session = Depends(get_db)) -> dict[str, str]:
    todo("A-05")
