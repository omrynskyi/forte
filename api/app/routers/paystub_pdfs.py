"""Paystub PDF download (PAY-3, TERM-2, D16). Task A-13.

Authorization FIRST, before touching storage:
- caller is the employee on that stub (actor.employee_id == item.employee_id), ACTIVE or FORMER;
- and the stub's company_id == actor.company_id (else 404, never reveal existence);
- the stub is final (a Paystub row exists) and pdf_object_key is set, else 409 "pdf_not_ready".
Then:
- GET .../pdf       -> PaystubPdfLink: presigned GET URL, valid settings.paystub_url_ttl_seconds (60),
                       signed against settings.s3_public_endpoint, Content-Disposition attachment.
- GET .../pdf/file  -> streams the bytes through the API (fallback if presigning misbehaves, e.g.
                       a phone that can't reach MinIO directly). Same authorization.
Both write nothing; no audit entry needed for an employee reading their own stub.
"""

import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.adapters import get_storage
from app.adapters.storage import StorageAdapter
from app.auth.deps import Actor, require_employee_self
from app.db import get_db
from app.errors import todo
from app.schemas.paystubs import PaystubPdfLink

router = APIRouter(prefix="/api/me/paystubs", tags=["paystubs"])


@router.get("/{item_id}/pdf", response_model=PaystubPdfLink)
def paystub_pdf_link(
    item_id: uuid.UUID,
    actor: Actor = Depends(require_employee_self(allow_former=True)),
    db: Session = Depends(get_db),
    storage: StorageAdapter = Depends(get_storage),
):
    todo("A-13")


@router.get(
    "/{item_id}/pdf/file",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}},
)
def paystub_pdf_file(
    item_id: uuid.UUID,
    actor: Actor = Depends(require_employee_self(allow_former=True)),
    db: Session = Depends(get_db),
    storage: StorageAdapter = Depends(get_storage),
):
    todo("A-13")
