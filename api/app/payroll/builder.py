"""Run builder (RUN-1, EMP-5, NFR-2). Task A-03.

    build_regular_run(db, run: PayrollRun, tax: TaxProvider, as_of: date) -> list[Blocker]

- Run must be DRAFT (the DB trigger rejects item writes otherwise). Delete existing items first.
- Employees: ACTIVE, in the run's company, hire_date <= period.end_date. For each, call
  services.readiness.readiness(); not ready -> a blocker (excluded from the run), not an error.
- Gross: salary -> money.salary_per_period(annual); hourly -> money.hourly_gross(rate,
  services.timesheets.approved_minutes(...)). Hourly employee with 0 approved minutes -> no item.
  Rate = compensation effective on period.end_date.
- Taxes: ONE batched tax.calculate([...]) call. TaxProviderError -> leave run untouched, 503.
- Item: net = gross - employee taxes; employer_cost = gross + employer taxes; bank_account_id =
  current verified deposit account.
- Totals: recompute from the items (sum) and set calculated_at. Audit RUN_RECALCULATED.
Also export `apply_tax_result(item, result)` and `recompute_totals(run, items)`: corrections (A-07)
and final paychecks (A-08) reuse them, so every run type computes money the same way.
"""
