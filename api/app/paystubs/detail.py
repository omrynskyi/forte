"""Builds paystub API objects from payroll items (A-06; reused by A-12 for the PDF).

A paystub's id is its payroll_item_id (D24). Previews have no Paystub row; they are read straight
from items of submitted/approved/processing/failed runs. Callers get tenant and visibility checks
from `visible_item_or_404`.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import Actor
from app.errors import NotFound
from app.models import (
    BankAccount,
    Company,
    Correction,
    Employee,
    PayPeriod,
    PayrollItem,
    PayrollRun,
    Paystub,
)
from app.models.enums import PayType, RunState, RunType
from app.money import format_cents, format_hours
from app.payroll.states import PREVIEW_STATES, correction_status
from app.paystubs import templates
from app.schemas.paystubs import CorrectionBrief, PaystubDetail, PaystubLine, PaystubSummary

VISIBLE_STATES = (RunState.PAID, *PREVIEW_STATES)


def employee_taxes_cents(item: PayrollItem) -> int:
    return (
        item.fed_income_tax_cents
        + item.social_security_cents
        + item.medicare_cents
        + item.ca_pit_cents
        + item.ca_sdi_cents
    )


def visible_item_or_404(
    db: Session, item_id: uuid.UUID, actor: Actor, *, employee_id: uuid.UUID | None
) -> tuple[PayrollItem, PayrollRun]:
    """The item and its run if it is in this company, visible (PAID or preview state), and, when
    `employee_id` is given, belongs to that employee. Otherwise the same 404 for every case."""
    row = db.execute(
        select(PayrollItem, PayrollRun)
        .join(PayrollRun, PayrollRun.id == PayrollItem.run_id)
        .where(
            PayrollItem.id == item_id,
            PayrollItem.company_id == actor.company_id,
            PayrollRun.company_id == actor.company_id,
            PayrollRun.state.in_(VISIBLE_STATES),
        )
    ).first()
    if row is None or (employee_id is not None and row[0].employee_id != employee_id):
        raise NotFound("Paystub not found.")
    return row[0], row[1]


def _pdf_available(db: Session, item_id: uuid.UUID) -> bool:
    key = db.scalar(select(Paystub.pdf_object_key).where(Paystub.payroll_item_id == item_id))
    return key is not None


def corrections_for(db: Session, item: PayrollItem) -> list[CorrectionBrief]:
    rows = db.execute(
        select(Correction, PayrollRun)
        .join(PayrollRun, PayrollRun.id == Correction.correction_run_id)
        .where(Correction.original_item_id == item.id, Correction.company_id == item.company_id)
        .order_by(Correction.created_at)
    ).all()
    out = []
    for corr, run in rows:
        corr_item = db.scalars(
            select(PayrollItem).where(
                PayrollItem.run_id == run.id, PayrollItem.employee_id == corr.employee_id
            )
        ).first()
        out.append(
            CorrectionBrief(
                id=corr.id,
                status=correction_status(run.state),
                reason=corr.reason.value,
                missed_minutes=corr.missed_minutes,
                gross_cents=corr_item.gross_cents if corr_item else 0,
                correction_item_id=corr_item.id if corr_item else None,
                created_at=corr.created_at,
            )
        )
    return out


def _corrects(db: Session, item: PayrollItem) -> Correction | None:
    return db.scalars(
        select(Correction).where(
            Correction.correction_run_id == item.run_id,
            Correction.employee_id == item.employee_id,
        )
    ).first()


def build_paystub_summary(db: Session, item: PayrollItem, run: PayrollRun) -> PaystubSummary:
    corrects = _corrects(db, item)
    return PaystubSummary(
        id=item.id,
        run_id=run.id,
        run_type=run.run_type,
        pay_date=run.pay_date,
        is_preview=run.state != RunState.PAID,
        gross_cents=item.gross_cents,
        net_cents=item.net_cents,
        corrections=corrections_for(db, item),
        corrects_item_id=corrects.original_item_id if corrects else None,
        pdf_available=run.state == RunState.PAID and _pdf_available(db, item.id),
    )


def _headline(db: Session, item: PayrollItem, run: PayrollRun, corrects: Correction | None) -> str:
    gross = format_cents(item.gross_cents)
    taxes = format_cents(employee_taxes_cents(item))
    net = format_cents(item.net_cents)
    if run.run_type == RunType.CORRECTION and corrects is not None:
        orig_date = db.scalar(
            select(PayrollRun.pay_date)
            .join(PayrollItem, PayrollItem.run_id == PayrollRun.id)
            .where(PayrollItem.id == corrects.original_item_id)
        )
        if orig_date is not None:
            return templates.correction_headline(
                gross, format_hours(corrects.missed_minutes), orig_date, taxes, net
            )
    if run.run_type == RunType.FINAL:
        return templates.final_headline(gross, taxes, net)
    if item.pay_type == PayType.HOURLY:
        return templates.hourly_headline(
            gross, format_hours(item.minutes or 0), format_cents(item.rate_cents), taxes, net
        )
    return templates.salary_headline(gross, taxes, net)


def _line(code: str, cents: int) -> PaystubLine:
    label, explanation = templates.LINES[code]
    return PaystubLine(code=code, label=label, amount_cents=cents, explanation=explanation)


def build_paystub_detail(db: Session, item: PayrollItem) -> PaystubDetail:
    run = db.get(PayrollRun, item.run_id)
    company = db.get(Company, item.company_id)
    emp = db.get(Employee, item.employee_id)
    assert run is not None and company is not None and emp is not None
    summary = build_paystub_summary(db, item, run)
    period = db.get(PayPeriod, run.pay_period_id) if run.pay_period_id else None
    corrects = _corrects(db, item)
    acct = db.get(BankAccount, item.bank_account_id) if item.bank_account_id else None

    street = ", ".join(p for p in (company.address_line1, company.address_line2) if p)
    address = f"{street}, {company.city}, {company.state} {company.zip}"

    return PaystubDetail(
        **summary.model_dump(),
        period_start=period.start_date if period else None,
        period_end=period.end_date if period else None,
        employer_name=company.legal_name,
        employer_address=address,
        employee_name=f"{emp.first_name} {emp.last_name}",
        employee_number=emp.employee_number,
        ssn_last4=emp.ssn_last4,
        pay_type=item.pay_type,
        minutes=item.minutes,
        rate_cents=item.rate_cents,
        memo=item.memo,
        headline=_headline(db, item, run, corrects),
        earnings=[_line("gross", item.gross_cents)],
        taxes=[_line(code, getattr(item, f"{code}_cents")) for code in templates.TAX_CODES],
        employee_taxes_cents=employee_taxes_cents(item),
        deposit_account_last4=acct.account_last4 if acct else None,
    )
