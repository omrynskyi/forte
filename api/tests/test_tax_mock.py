"""MockTaxProvider (A-01, D6). Pure function, no database needed."""

import uuid
from dataclasses import replace
from datetime import date

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.adapters.mock.tax import CALCULATION_REF, MockTaxProvider
from app.adapters.tax import TaxRequest, TaxResult
from app.models.enums import CaFilingStatus, FedFilingStatus

GOLDEN_GROSS = 196_000  # 80h x $24.50


def _req(**overrides) -> TaxRequest:
    fields = {
        "employee_id": uuid.uuid4(),
        "pay_date": date(2026, 11, 13),
        "gross_cents": GOLDEN_GROSS,
        "pay_periods_per_year": 26,
        "fed_filing_status": FedFilingStatus.SINGLE,
        "fed_multiple_jobs": False,
        "fed_dependents_cents": 0,
        "fed_extra_cents": 0,
        "ca_filing_status": CaFilingStatus.SINGLE,
        "ca_allowances": 0,
        "ca_extra_cents": 0,
    }
    fields.update(overrides)
    return TaxRequest(**fields)


def _calc(**overrides) -> TaxResult:
    [result] = MockTaxProvider().calculate([_req(**overrides)])
    return result


def test_golden_case():
    r = _calc()
    assert r.fed_income_tax_cents == 23_520
    assert r.social_security_cents == 12_152
    assert r.medicare_cents == 2_842
    assert r.ca_pit_cents == 7_840
    assert r.ca_sdi_cents == 2_548
    assert r.employee_taxes_cents == 48_902
    assert GOLDEN_GROSS - r.employee_taxes_cents == 147_098
    assert r.employer_social_security_cents == 12_152
    assert r.employer_medicare_cents == 2_842
    assert r.futa_cents == 1_176
    assert r.ca_sui_cents == 6_664
    assert r.ca_ett_cents == 196
    assert r.calculation_ref == CALCULATION_REF == "mock-tax-v1"


@pytest.mark.parametrize(
    ("fed_status", "ca_status", "fed", "ca_pit"),
    [
        (FedFilingStatus.SINGLE, CaFilingStatus.SINGLE, 23_520, 7_840),  # 12% / 4%
        (FedFilingStatus.MARRIED_JOINTLY, CaFilingStatus.MARRIED, 19_600, 5_880),  # 10% / 3%
        (FedFilingStatus.HEAD_OF_HOUSEHOLD, CaFilingStatus.HEAD_OF_HOUSEHOLD, 21_560, 6_860),
    ],
)
def test_filing_status_rates(fed_status, ca_status, fed, ca_pit):
    r = _calc(fed_filing_status=fed_status, ca_filing_status=ca_status)
    assert r.fed_income_tax_cents == fed
    assert r.ca_pit_cents == ca_pit
    # FICA, SDI and employer taxes don't depend on filing status
    assert (r.social_security_cents, r.medicare_cents, r.ca_sdi_cents) == (12_152, 2_842, 2_548)
    assert r.employer_taxes_cents == 12_152 + 2_842 + 1_176 + 6_664 + 196


@pytest.mark.parametrize(
    ("fed_status", "fed"),
    [
        (FedFilingStatus.SINGLE, 27_440),  # 14%
        (FedFilingStatus.MARRIED_JOINTLY, 23_520),  # 12%
        (FedFilingStatus.HEAD_OF_HOUSEHOLD, 25_480),  # 13%
    ],
)
def test_multiple_jobs_adds_200_bp(fed_status, fed):
    assert _calc(fed_filing_status=fed_status, fed_multiple_jobs=True).fed_income_tax_cents == fed


def test_dependents_reduce_federal_taxable_pay():
    # $2,000/yr over 26 periods = 7692.31 -> 7692 per period (half-up)
    # (196000 - 7692) x 12% = 22596.96 -> 22597
    assert _calc(fed_dependents_cents=200_000).fed_income_tax_cents == 22_597


def test_dependents_per_period_round_half_up():
    # 13 / 26 = 0.5 rounds up to 1 cent: (5 - 1) x 12% = 0.48 -> 0.
    # 12 / 26 = 0.46 rounds down to 0:     (5 - 0) x 12% = 0.60 -> 1.
    assert _calc(gross_cents=5, fed_dependents_cents=13).fed_income_tax_cents == 0
    assert _calc(gross_cents=5, fed_dependents_cents=12).fed_income_tax_cents == 1


def test_dependents_larger_than_gross_zero_federal():
    r = _calc(fed_dependents_cents=8_000_000)  # 307692 per period > 196000 gross
    assert r.fed_income_tax_cents == 0
    # extra withholding still applies on top of a zero base
    assert (
        _calc(fed_dependents_cents=8_000_000, fed_extra_cents=1_000).fed_income_tax_cents == 1_000
    )


def test_ca_allowances():
    assert _calc(ca_allowances=2).ca_pit_cents == 7_840 - 2 * 500
    assert _calc(ca_allowances=20).ca_pit_cents == 0  # $100 of allowances > $78.40 base
    assert _calc(ca_allowances=20, ca_extra_cents=300).ca_pit_cents == 300


def test_extra_withholding():
    r = _calc(fed_extra_cents=5_000, ca_extra_cents=2_500)
    assert r.fed_income_tax_cents == 23_520 + 5_000
    assert r.ca_pit_cents == 7_840 + 2_500
    assert r.employee_taxes_cents == 48_902 + 7_500


def test_gross_zero():
    r = _calc(gross_cents=0)
    assert r.employee_taxes_cents == 0
    assert r.employer_taxes_cents == 0


def test_gross_zero_with_extras_withholds_nothing():
    r = _calc(gross_cents=0, fed_extra_cents=5_000, ca_extra_cents=2_500)
    assert r.fed_income_tax_cents == 0
    assert r.ca_pit_cents == 0


def test_cap_trims_fed_extra_first():
    # gross $100: base lines ss 620 + medicare 145 + sdi 130 + fed 1200 + ca 400 = 2495
    # extras 5000 + 5000 push taxes to 12495, 2495 over gross: all of it comes off fed_extra.
    r = _calc(gross_cents=10_000, fed_extra_cents=5_000, ca_extra_cents=5_000)
    assert r.fed_income_tax_cents == 1_200 + 2_505
    assert r.ca_pit_cents == 400 + 5_000
    assert r.employee_taxes_cents == 10_000  # net exactly 0


def test_cap_trims_ca_extra_after_fed_extra_is_gone():
    # Same base 2495; extras 1000 + 9000 are 2495 over. fed_extra goes to 0, ca_extra loses 1495.
    r = _calc(gross_cents=10_000, fed_extra_cents=1_000, ca_extra_cents=9_000)
    assert r.fed_income_tax_cents == 1_200
    assert r.ca_pit_cents == 400 + 7_505
    assert r.employee_taxes_cents == 10_000


def test_cap_does_not_touch_employer_taxes():
    capped = _calc(gross_cents=10_000, fed_extra_cents=50_000)
    plain = _calc(gross_cents=10_000)
    assert capped.employer_taxes_cents == plain.employer_taxes_cents


def test_batch_keeps_order_and_ids():
    reqs = [
        _req(gross_cents=GOLDEN_GROSS),
        _req(gross_cents=0),
        _req(gross_cents=300_000, fed_filing_status=FedFilingStatus.MARRIED_JOINTLY),
    ]
    results = MockTaxProvider().calculate(reqs)
    assert [r.employee_id for r in results] == [q.employee_id for q in reqs]
    assert results[0].fed_income_tax_cents == 23_520
    assert results[1].fed_income_tax_cents == 0
    assert results[2].fed_income_tax_cents == 30_000
    assert results == [MockTaxProvider().calculate([q])[0] for q in reqs]


def test_empty_batch():
    assert MockTaxProvider().calculate([]) == []


def test_deterministic():
    req = _req(fed_dependents_cents=200_000, fed_extra_cents=1_234, ca_allowances=3)
    assert MockTaxProvider().calculate([req]) == MockTaxProvider().calculate([req])


@pytest.mark.parametrize(
    "overrides",
    [
        {"gross_cents": -1},
        {"fed_dependents_cents": -1},
        {"fed_extra_cents": -1},
        {"ca_allowances": -1},
        {"ca_extra_cents": -1},
        {"pay_periods_per_year": 0},
    ],
)
def test_rejects_invalid_input(overrides):
    with pytest.raises(ValueError):
        _calc(**overrides)


requests = st.builds(
    _req,
    gross_cents=st.integers(0, 10**9),
    pay_periods_per_year=st.sampled_from([1, 12, 24, 26, 52]),
    fed_filing_status=st.sampled_from(FedFilingStatus),
    fed_multiple_jobs=st.booleans(),
    fed_dependents_cents=st.integers(0, 10**8),
    fed_extra_cents=st.integers(0, 10**8),
    ca_filing_status=st.sampled_from(CaFilingStatus),
    ca_allowances=st.integers(0, 50),
    ca_extra_cents=st.integers(0, 10**8),
)


@given(requests)
def test_outputs_are_non_negative_ints_and_never_exceed_gross(req):
    [r] = MockTaxProvider().calculate([req])
    cents = [
        r.fed_income_tax_cents,
        r.social_security_cents,
        r.medicare_cents,
        r.ca_pit_cents,
        r.ca_sdi_cents,
        r.employer_social_security_cents,
        r.employer_medicare_cents,
        r.futa_cents,
        r.ca_sui_cents,
        r.ca_ett_cents,
    ]
    assert all(type(c) is int and c >= 0 for c in cents)
    assert r.employee_taxes_cents <= req.gross_cents


@given(requests)
def test_extras_are_only_trimmed_to_reach_zero_net(req):
    [with_extras] = MockTaxProvider().calculate([req])
    [base] = MockTaxProvider().calculate([replace(req, fed_extra_cents=0, ca_extra_cents=0)])
    uncapped = base.employee_taxes_cents + req.fed_extra_cents + req.ca_extra_cents
    if uncapped <= req.gross_cents:
        assert with_extras.employee_taxes_cents == uncapped
    else:
        assert with_extras.employee_taxes_cents == req.gross_cents
    # the trimmed extras never go below zero or above what the employee asked for
    fed_extra = with_extras.fed_income_tax_cents - base.fed_income_tax_cents
    ca_extra = with_extras.ca_pit_cents - base.ca_pit_cents
    assert 0 <= fed_extra <= req.fed_extra_cents
    assert 0 <= ca_extra <= req.ca_extra_cents
    # ca_extra is only touched once fed_extra is used up
    if ca_extra < req.ca_extra_cents:
        assert fed_extra == 0
