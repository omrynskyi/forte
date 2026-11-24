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
from app.errors import todo
from app.models.enums import CaFilingStatus, FedFilingStatus

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
        todo("A-01")
