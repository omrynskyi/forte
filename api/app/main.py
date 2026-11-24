"""FastAPI app. Every router is registered here already, so tasks never need to edit this file."""

from fastapi import FastAPI

from app.errors import install_error_handlers
from app.routers import (
    audit,
    auth,
    company,
    corrections,
    dashboard,
    employees,
    health,
    me,
    members,
    paystub_pdfs,
    paystubs,
    runs,
    terminations,
    timesheets,
    webhooks,
)

app = FastAPI(
    title="Forte API",
    version="0.1.0",
    description="Payroll MVP for CMPE 272. California W-2 only. All money is integer cents.",
)
install_error_handlers(app)

for module in (
    health,
    auth,
    company,
    members,
    employees,
    terminations,
    me,
    timesheets,
    runs,
    webhooks,
    paystubs,
    paystub_pdfs,
    corrections,
    dashboard,
    audit,
):
    app.include_router(module.router)
