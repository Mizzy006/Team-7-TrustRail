"""Thin entrypoint: run uvicorn on app.main:app port 8001."""

from __future__ import annotations

import uvicorn

from app.main import app

__all__ = ["app"]

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8001, reload=True)
