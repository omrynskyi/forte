"""All user-facing paystub copy (PAY-1). Written by us, stored here, never generated on the fly.

Money and hours arrive pre-formatted (`format_cents`, `format_hours`), so nothing here does math.
"""

from datetime import date

# code -> (label, one plain-language line)
LINES: dict[str, tuple[str, str]] = {
    "gross": ("Gross pay", "Everything you earned this pay period, before anything was taken out."),
    "fed_income_tax": ("Federal income tax", "Based on your W-4"),
    "social_security": ("Social Security", "6.2% of what you earned"),
    "medicare": ("Medicare", "1.45% of what you earned"),
    "ca_pit": ("California income tax", "Based on your DE 4 and California rules"),
    "ca_sdi": ("California disability insurance", "Paid into the state's disability fund"),
}

TAX_CODES = ("fed_income_tax", "social_security", "medicare", "ca_pit", "ca_sdi")

PREVIEW_NOTE = "This is a preview. It becomes final once payroll is approved."


def short_date(d: date) -> str:
    """date(2026, 10, 30) -> 'Oct 30' (no zero padding)."""
    return f"{d.strftime('%b')} {d.day}"


def _tail(taxes: str, net: str) -> str:
    return f"{taxes} went to taxes and the disability fund. You take home {net}."


def hourly_headline(gross: str, hours: str, rate: str, taxes: str, net: str) -> str:
    return f"You earned {gross} for {hours} hours at {rate} an hour. {_tail(taxes, net)}"


def salary_headline(gross: str, taxes: str, net: str) -> str:
    return f"You earned {gross} in salary for this pay period. {_tail(taxes, net)}"


def correction_headline(
    gross: str, hours: str, original_pay_date: date, taxes: str, net: str
) -> str:
    return (
        f"You earned {gross} for {hours} hours you were owed on your "
        f"{short_date(original_pay_date)} paycheck. {_tail(taxes, net)}"
    )


def final_headline(gross: str, taxes: str, net: str) -> str:
    return (
        f"This is your final paycheck. You earned {gross} for your last days of work. "
        f"{_tail(taxes, net)}"
    )
