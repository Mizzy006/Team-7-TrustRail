from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["Owner"])


@router.get("/healthz")
def healthz():
    return {"status": "ok"}
