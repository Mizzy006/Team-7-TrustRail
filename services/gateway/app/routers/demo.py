from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.auth import AuthContext, require_owner
from app.config import get_settings
from app.db import get_db
from app.errors import Forbidden, NotFound
from app.models import AuditLog
from app.schemas import TamperAuditRequest
from app.seed import reseed

router = APIRouter(prefix="/demo/v1", tags=["Demo"])


def _require_demo_mode() -> None:
    if not get_settings().demo_mode:
        raise Forbidden("Demo endpoints disabled (DEMO_MODE=false)")


@router.post("/reset", status_code=204)
def reset_demo(
    auth: AuthContext = Depends(require_owner),
    db: Session = Depends(get_db),
):
    _require_demo_mode()
    reseed(db)
    return Response(status_code=204)


@router.post("/tamper-audit", status_code=204)
def tamper_audit(
    body: TamperAuditRequest,
    auth: AuthContext = Depends(require_owner),
    db: Session = Depends(get_db),
):
    _require_demo_mode()
    row = db.query(AuditLog).filter(AuditLog.seq == body.seq).one_or_none()
    if row is None:
        raise NotFound(f"Audit seq {body.seq} not found")
    # Mutate data so hash verification fails
    data = dict(row.data or {})
    data["__tampered"] = True
    row.data = data
    db.commit()
    return Response(status_code=204)
