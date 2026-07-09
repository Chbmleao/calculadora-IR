"""Data-ingestion endpoints (task 02).

- ``POST /api/import/{kind}`` — multipart upload of a B3 export (``kind`` is one of
  ``positions`` | ``transactions`` | ``proventos``). Returns an import summary. A
  malformed file raises ``ValueError`` in the importer, which the shared handler
  maps to HTTP 400 ``{"error": "...faltando coluna(s)..."}``.
- ``GET /api/imports/status`` — row counts + last import timestamp per table.

This module is auto-discovered by ``app.api.register_routers`` and mounted under
``/api``; it never edits shared wiring.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from app.db import get_db
from app.ingestion import service
from app.ingestion.schemas import ImportStatus, ImportSummary

router = APIRouter(tags=["imports"])


@router.post("/import/{kind}", response_model=ImportSummary)
async def import_export(
    kind: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> ImportSummary:
    content = await file.read()
    summary = service.import_file(db, kind, content, file.filename)
    return ImportSummary(**summary)


@router.get("/imports/status", response_model=ImportStatus)
def imports_status(db: Session = Depends(get_db)) -> ImportStatus:
    return ImportStatus.model_validate(service.import_status(db))
