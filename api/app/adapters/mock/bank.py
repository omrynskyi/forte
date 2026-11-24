"""Mock BankVerifier. Rule (documented in DECISIONS.md so the demo can show a failure):
  - routing number fails the ABA checksum        -> failed, "That routing number isn't valid."
  - account number ends in 0000                  -> failed, "The bank couldn't confirm this account."
  - otherwise                                    -> verified
Good demo routing number: 110000000 (passes the checksum).
"""

import uuid

from app.adapters.bank import BankVerification, aba_checksum_ok


class MockBankVerifier:
    def verify(self, routing_number: str, account_number: str) -> BankVerification:
        ref = f"bv_{uuid.uuid4().hex[:12]}"
        if not aba_checksum_ok(routing_number):
            return BankVerification("failed", ref, "That routing number isn't valid.")
        if account_number.endswith("0000"):
            return BankVerification("failed", ref, "The bank couldn't confirm this account.")
        return BankVerification("verified", ref)
