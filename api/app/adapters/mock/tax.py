"""Mock TaxProvider (D6). Task A-01.

Simplified, deterministic, CLEARLY NOT REAL withholding. Rates are integer basis points and every
line is rounded half-up once via app.money.apply_bp. No wage bases or YTD caps in the MVP.

Per paycheck, for gross G:
  social_security        = G x 6.20%            (620 bp)   employee AND employer
  medicare               = G x 1.45%            (145 bp)   employee AND employer
  ca_sdi                 = G x 1.30%            (130 bp)   employee only
  futa                   = G x 0.60%            (60 bp)    employer only
  ca_sui                 = G x 3.40%            (340 bp)   employer only (new CA employer rate)
  ca_ett                 = G x 0.10%            (10 bp)    employer only
  fed_income_tax         = max(0, (G - dependents/periods) x FED_RATE[status] (+200 bp if
                           multiple_jobs)) + fed_extra
  ca_pit                 = max(0, G x CA_RATE[status] - allowances x $5.00) + ca_extra
  (dependents/periods rounded half-up)

Golden case (must be a test): G = 196000 (80h x $24.50), single, no extras, 0 allowances
  -> fed 23520, ss 12152, medicare 2842, ca_pit 7840, ca_sdi 2548; employee taxes 48902,
     net 147098; employer ss 12152, medicare 2842, futa 1176, sui 6664, ett 196.
"""

from app.adapters.tax import TaxRequest, TaxResult
from app.models.enums import CaFilingStatus, FedFilingStatus
from app.money import apply_bp, round_half_up_div

CALCULATION_REF = "mock-tax-v1"

SOCIAL_SECURITY_BP = 620
MEDICARE_BP = 145
CA_SDI_BP = 130
FUTA_BP = 60
CA_SUI_BP = 340
CA_ETT_BP = 10
FED_RATE_BP = {
    FedFilingStatus.SINGLE: 1200,
    FedFilingStatus.MARRIED_JOINTLY: 1000,
    FedFilingStatus.HEAD_OF_HOUSEHOLD: 1100,
}
FED_MULTIPLE_JOBS_EXTRA_BP = 200
CA_RATE_BP = {
    CaFilingStatus.SINGLE: 400,
    CaFilingStatus.MARRIED: 300,
    CaFilingStatus.HEAD_OF_HOUSEHOLD: 350,
}
CA_ALLOWANCE_CENTS = 500


class MockTaxProvider:
    def calculate(self, requests: list[TaxRequest]) -> list[TaxResult]:
        """One result per request, same order. Pure: no DB, no network, no randomness."""
        return [_calculate_one(r) for r in requests]


def _validate(r: TaxRequest) -> None:
    if r.pay_periods_per_year <= 0:
        raise ValueError("pay_periods_per_year must be positive")
    for name in (
        "gross_cents",
        "fed_dependents_cents",
        "fed_extra_cents",
        "ca_allowances",
        "ca_extra_cents",
    ):
        if getattr(r, name) < 0:
            raise ValueError(f"{name} must not be negative")


def _calculate_one(r: TaxRequest) -> TaxResult:
    _validate(r)
    gross = r.gross_cents

    social_security = apply_bp(gross, SOCIAL_SECURITY_BP)
    medicare = apply_bp(gross, MEDICARE_BP)
    ca_sdi = apply_bp(gross, CA_SDI_BP)

    dependents_per_period = round_half_up_div(r.fed_dependents_cents, r.pay_periods_per_year)
    fed_rate = FED_RATE_BP[r.fed_filing_status]
    if r.fed_multiple_jobs:
        fed_rate += FED_MULTIPLE_JOBS_EXTRA_BP
    fed_base = apply_bp(max(0, gross - dependents_per_period), fed_rate)

    ca_base = max(
        0, apply_bp(gross, CA_RATE_BP[r.ca_filing_status]) - r.ca_allowances * CA_ALLOWANCE_CENTS
    )

    # Withholding never exceeds gross. At these rates the computed lines (everything except the
    # extras) total at most ~27% of gross, so only the extras can push net below zero: trim
    # fed_extra first, then ca_extra, until net is exactly 0.
    fed_extra = r.fed_extra_cents
    ca_extra = r.ca_extra_cents
    excess = social_security + medicare + ca_sdi + fed_base + ca_base + fed_extra + ca_extra - gross
    if excess > 0:
        cut = min(excess, fed_extra)
        fed_extra -= cut
        excess -= cut
        ca_extra -= min(excess, ca_extra)

    return TaxResult(
        employee_id=r.employee_id,
        fed_income_tax_cents=fed_base + fed_extra,
        social_security_cents=social_security,
        medicare_cents=medicare,
        ca_pit_cents=ca_base + ca_extra,
        ca_sdi_cents=ca_sdi,
        employer_social_security_cents=apply_bp(gross, SOCIAL_SECURITY_BP),
        employer_medicare_cents=apply_bp(gross, MEDICARE_BP),
        futa_cents=apply_bp(gross, FUTA_BP),
        ca_sui_cents=apply_bp(gross, CA_SUI_BP),
        ca_ett_cents=apply_bp(gross, CA_ETT_BP),
        calculation_ref=CALCULATION_REF,
    )
