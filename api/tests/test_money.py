from datetime import date

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.money import (
    apply_bp,
    format_cents,
    format_hours,
    hourly_gross,
    prorate_salary,
    round_half_up_div,
    salary_per_period,
    workdays_between,
)


@pytest.mark.parametrize(
    ("num", "den", "expected"),
    [
        (5, 2, 3),
        (4, 2, 2),
        (7, 2, 4),
        (-5, 2, -3),
        (1, 3, 0),
        (2, 3, 1),
        (149, 100, 1),
        (150, 100, 2),
    ],
)
def test_round_half_up_div(num, den, expected):
    assert round_half_up_div(num, den) == expected


@given(st.integers(-(10**12), 10**12), st.integers(1, 10**6))
def test_round_half_up_is_within_half(num, den):
    q = round_half_up_div(num, den)
    assert abs(q * den - num) * 2 <= den


def test_rates_and_pay():
    assert apply_bp(196000, 620) == 12152  # Social Security on $1,960.00
    assert apply_bp(196000, 145) == 2842  # Medicare
    assert salary_per_period(7_800_000) == 300_000  # $78,000 / 26
    assert hourly_gross(2450, 80 * 60) == 196_000  # 80h at $24.50
    assert hourly_gross(2200, 6 * 60 + 30) == 14_300  # 6.5h at $22.00 (design's correction)


def test_proration_workdays():
    # Nov 23 (Mon) .. Dec 6 (Sun) 2026 has 10 workdays; terminated Wed Dec 2 -> 8 worked.
    assert workdays_between(date(2026, 11, 23), date(2026, 12, 6)) == 10
    assert workdays_between(date(2026, 11, 23), date(2026, 12, 2)) == 8
    assert prorate_salary(300_000, 8, 10) == 240_000
    assert prorate_salary(300_000, 6, 10) == 180_000


def test_formatting():
    assert format_cents(1_234_567) == "$12,345.67"
    assert format_cents(-5) == "-$0.05"
    assert format_hours(480) == "8.0"
    assert format_hours(390) == "6.5"
    assert format_hours(75) == "1.25"
