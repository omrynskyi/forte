"""BankVerifier interface (CO-2, ONB-1). Stands in for Plaid / micro-deposit verification."""

from dataclasses import dataclass
from typing import Literal, Protocol


@dataclass(frozen=True)
class BankVerification:
    status: Literal["verified", "failed"]
    provider_ref: str
    reason: str | None = None  # plain-language, shown to the user on failure


class BankVerifier(Protocol):
    def verify(self, routing_number: str, account_number: str) -> BankVerification: ...


def aba_checksum_ok(routing_number: str) -> bool:
    """ABA routing number checksum: 3*(d1+d4+d7) + 7*(d2+d5+d8) + (d3+d6+d9) ≡ 0 (mod 10)."""
    if len(routing_number) != 9 or not routing_number.isdigit():
        return False
    d = [int(c) for c in routing_number]
    total = 3 * (d[0] + d[3] + d[6]) + 7 * (d[1] + d[4] + d[7]) + (d[2] + d[5] + d[8])
    return total % 10 == 0
