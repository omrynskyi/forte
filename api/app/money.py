"""Integer-cents money math. NFR-1: no floats anywhere money is handled.

Every function takes and returns `int` cents. Rates are integer basis points (1% = 100 bp).
Rounding rule (D6): round half up, away from zero, applied once per line item.
"""

from datetime import date, timedelta

PERIODS_PER_YEAR = {"biweekly": 26}


def round_half_up_div(numerator: int, denominator: int) -> int:
    """Divide two ints and round half away from zero. Exact, no floats."""
    if denominator == 0:
        raise ZeroDivisionError("denominator is 0")
    if denominator < 0:
        numerator, denominator = -numerator, -denominator
    sign = -1 if numerator < 0 else 1
    q, r = divmod(abs(numerator), denominator)
    if r * 2 >= denominator:
        q += 1
    return sign * q


def apply_bp(cents: int, basis_points: int) -> int:
    """cents x rate. 6.2% is 620 bp, 1.45% is 145 bp."""
    return round_half_up_div(cents * basis_points, 10_000)


def salary_per_period(annual_cents: int, schedule: str = "biweekly") -> int:
    return round_half_up_div(annual_cents, PERIODS_PER_YEAR[schedule])


def hourly_gross(rate_cents_per_hour: int, minutes: int) -> int:
    """Hours are stored as integer minutes. No overtime in the MVP (D3)."""
    return round_half_up_div(rate_cents_per_hour * minutes, 60)


def workdays_between(start: date, end: date) -> int:
    """Mon-Fri days in [start, end], inclusive. 0 if end < start."""
    if end < start:
        return 0
    days = 0
    d = start
    while d <= end:
        if d.weekday() < 5:
            days += 1
        d += timedelta(days=1)
    return days


def prorate_salary(period_cents: int, worked_days: int, total_days: int) -> int:
    """Final paycheck proration (decision D15): period salary x workdays worked / workdays in period."""
    if total_days <= 0:
        return 0
    return round_half_up_div(period_cents * worked_days, total_days)


def format_cents(cents: int) -> str:
    """1234567 -> '$12,345.67'. For server-rendered text (paystub sentences, emails)."""
    sign = "-" if cents < 0 else ""
    dollars, rest = divmod(abs(cents), 100)
    return f"{sign}${dollars:,}.{rest:02d}"


def format_hours(minutes: int) -> str:
    """480 -> '8.0', 390 -> '6.5', 75 -> '1.25'. Displays hours without float math."""
    whole, rem = divmod(minutes, 60)
    hundredths = round_half_up_div(rem * 100, 60)
    if hundredths == 100:
        whole, hundredths = whole + 1, 0
    if hundredths % 10 == 0:
        return f"{whole}.{hundredths // 10}"
    return f"{whole}.{hundredths:02d}"
