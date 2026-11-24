"""Smoke tests for the skeleton: the app boots, the contract is published, stubs point at tasks."""

from app.adapters.bank import aba_checksum_ok
from app.adapters.mock.bank import MockBankVerifier
from app.services.readiness import readiness
from tests import factories as f


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_openapi_has_every_area(client):
    paths = client.get("/openapi.json").json()["paths"]
    for p in [
        "/api/auth/magic-link",
        "/api/companies",
        "/api/members",
        "/api/employees",
        "/api/me/profile",
        "/api/me/timesheet",
        "/api/runs",
        "/api/runs/{run_id}/approve",
        "/api/webhooks/payments",
        "/api/me/paystubs/{item_id}",
        "/api/me/paystubs/{item_id}/pdf",
        "/api/corrections",
        "/api/dashboard",
        "/api/audit",
    ]:
        assert p in paths, p


def test_unimplemented_endpoint_names_its_task(client, db, as_actor):
    company = f.make_company(db)
    as_actor(f.make_member(db, company))
    r = client.get("/api/dashboard")
    assert r.status_code == 501
    assert r.json()["detail"]["task"] == "A-09"


def test_mock_bank_verifier_rules():
    assert aba_checksum_ok("110000000")
    v = MockBankVerifier()
    assert v.verify("110000000", "000123453347").status == "verified"
    assert v.verify("110000000", "000123450000").status == "failed"
    assert v.verify("123456789", "000123453347").status == "failed"


def test_readiness(db):
    company = f.make_company(db)
    ready = f.make_employee(db, company)
    new = f.make_employee(db, company, "Rosa", "Delgado", onboarded=False)
    from datetime import date

    assert readiness(db, ready, date(2026, 12, 1)).ready
    r = readiness(db, new, date(2026, 12, 1))
    assert not r.ready
    assert r.missing == ["personal_info", "withholding", "bank_account"]
