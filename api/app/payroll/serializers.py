"""A-04: read-only run responses for staff, scoped to the caller's company.

Amounts come from stored payroll items/totals; GET never rebuilds pay. Readiness warnings
reflect current setup, with compensation checked at period end just as in the builder.
Members on payroll use their employee name; other staff use their sign-in email because
User has no display-name field. Missing hourly timesheets count as unapproved.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import clock
from app.auth.deps import Actor
from app.auth.scoping import get_scoped, scoped
from app.models import Employee, Membership, PayPeriod, PayrollItem, PayrollRun, Timesheet, User
from app.models.enums import EmploymentStatus, PayType, RunState, RunType
from app.payroll.builder import employee_taxes_cents
from app.payroll.state_machine import allowed_actions_for
from app.schemas.runs import (
    EmployerTaxLines,
    RunBlocker,
    RunDetail,
    RunItemOut,
    RunSummary,
    RunTotals,
    TaxLines,
)
from app.services.readiness import current_compensation, readiness
from app.services.timesheets import PAYABLE


def build_run_summary(db: Session, run: PayrollRun, actor: Actor) -> RunSummary:
    period = get_scoped(db, PayPeriod, run.pay_period_id, actor) if run.pay_period_id else None
    count = db.scalar(
        scoped(select(func.count()).select_from(PayrollItem), PayrollItem, actor).where(
            PayrollItem.run_id == run.id
        )
    )
    return RunSummary(
        id=run.id,
        run_type=run.run_type,
        state=run.state,
        pay_date=run.pay_date,
        period_start=period.start_date if period else None,
        period_end=period.end_date if period else None,
        cutoff_at=period.cutoff_at if period else None,
        at_risk=bool(
            period
            and run.state in (RunState.DRAFT, RunState.SUBMITTED)
            and clock.now() >= period.cutoff_at
        ),
        employee_count=count or 0,
        totals=RunTotals(
            gross_cents=run.total_gross_cents,
            employee_taxes_cents=run.total_employee_taxes_cents,
            deductions_cents=run.total_deductions_cents,
            net_cents=run.total_net_cents,
            employer_taxes_cents=run.total_employer_taxes_cents,
            company_cost_cents=run.total_company_cost_cents,
        ),
        original_run_id=run.original_run_id,
        created_at=run.created_at,
        submitted_at=run.submitted_at,
        approved_at=run.approved_at,
        paid_at=run.paid_at,
    )


def _member_name(db: Session, member_id, actor: Actor) -> str | None:
    if member_id is None:
        return None
    member = get_scoped(db, Membership, member_id, actor)
    if member.employee_id:
        employee = get_scoped(db, Employee, member.employee_id, actor)
        return f"{employee.first_name} {employee.last_name}"
    return db.get(User, member.user_id).email


def build_run_detail(db: Session, run: PayrollRun, actor: Actor) -> RunDetail:
    summary = build_run_summary(db, run, actor)
    rows = db.execute(
        scoped(
            select(PayrollItem, Employee).join(Employee, Employee.id == PayrollItem.employee_id),
            PayrollItem,
            actor,
        )
        .where(PayrollItem.run_id == run.id, Employee.company_id == actor.company_id)
        .order_by(Employee.last_name, Employee.first_name, Employee.employee_number)
    ).all()
    items = [
        RunItemOut(
            id=item.id,
            employee_id=employee.id,
            employee_name=f"{employee.first_name} {employee.last_name}",
            is_caller=employee.id == actor.employee_id,
            pay_type=item.pay_type,
            minutes=item.minutes,
            rate_cents=item.rate_cents,
            gross_cents=item.gross_cents,
            taxes=TaxLines.model_validate(item),
            employee_taxes_cents=employee_taxes_cents(item),
            net_cents=item.net_cents,
            employer_taxes=EmployerTaxLines(
                social_security_cents=item.employer_social_security_cents,
                medicare_cents=item.employer_medicare_cents,
                futa_cents=item.futa_cents,
                ca_sui_cents=item.ca_sui_cents,
                ca_ett_cents=item.ca_ett_cents,
            ),
            employer_cost_cents=item.employer_cost_cents,
            memo=item.memo,
        )
        for item, employee in rows
    ]
    blockers = []
    unapproved = 0
    if run.run_type == RunType.REGULAR:
        period = get_scoped(db, PayPeriod, run.pay_period_id, actor)
        employees = db.scalars(
            scoped(select(Employee), Employee, actor)
            .where(
                Employee.status == EmploymentStatus.ACTIVE, Employee.hire_date <= period.end_date
            )
            .order_by(Employee.last_name, Employee.first_name, Employee.employee_number)
        ).all()
        sheets = dict(
            db.execute(
                scoped(select(Timesheet.employee_id, Timesheet.status), Timesheet, actor).where(
                    Timesheet.pay_period_id == period.id
                )
            ).all()
        )
        for employee in employees:
            missing = list(readiness(db, employee, clock.today_pacific()).missing)
            comp = current_compensation(db, employee.id, period.end_date)
            if comp is None and "compensation" not in missing:
                missing.append("compensation")
            if missing:
                blockers.append(
                    RunBlocker(
                        employee_id=employee.id,
                        employee_name=f"{employee.first_name} {employee.last_name}",
                        missing=missing,
                    )
                )
            if comp and comp.pay_type == PayType.HOURLY and sheets.get(employee.id) not in PAYABLE:
                unapproved += 1
    return RunDetail(
        **summary.model_dump(),
        items=items,
        blockers=blockers,
        timesheets_unapproved=unapproved,
        allowed_actions=allowed_actions_for(db, run, actor),
        created_by_name=_member_name(db, run.created_by_membership_id, actor),
        submitted_by_name=_member_name(db, run.submitted_by_membership_id, actor),
        approved_by_name=_member_name(db, run.approved_by_membership_id, actor),
        failure_reason=run.failure_reason,
    )
