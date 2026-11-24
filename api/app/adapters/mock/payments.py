"""Mock PaymentsProvider (D8). Task A-05.

submit_payout(request):
  - Opens its OWN session (SessionLocal) and commits, like an external system would.
  - If a MockPayout with request.idempotency_key exists, return its receipt unchanged (NFR-3).
  - Else insert MockPayout(status=pending, provider_payout_id="po_<short uuid>").
  - Schedule a callback after settings.mock_payout_delay_seconds (default 5) on a daemon
    threading.Timer: POST settings.api_base_url + "/api/webhooks/payments" with a signed body
    (app.adapters.payments.sign), type "payout.paid" or "payout.failed" per
    settings.mock_payout_outcome. Mark callback_sent_at.
  - Tests: set mock_payout_delay_seconds=0 and inject a `dispatch` callable so the test can
    deliver the webhook through the TestClient instead of real HTTP.
"""

from app.adapters.payments import PayoutReceipt, PayoutRequest
from app.errors import todo


class MockPaymentsProvider:
    def submit_payout(self, request: PayoutRequest) -> PayoutReceipt:
        todo("A-05")
