"""Accounting (Bens e Direitos) endpoints (task 07), auto-mounted under ``/api``.

- ``GET  /api/accounting/bens-e-direitos``       -> JSON preview ``{assets, missing_cnpj}``.
- ``GET  /api/accounting/bens-e-direitos.xlsx``  -> streamed ``.xlsx`` download.
- ``POST /api/accounting/cnpj-overrides``        -> persist CNPJ overrides, report count.

All tax logic is reused from repo-root ``core.py`` via ``app.accounting.service`` —
this module is only the HTTP layer. Auto-discovered by ``app.api.register_routers``;
it never edits shared wiring.
"""

from __future__ import annotations

from io import BytesIO
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.accounting import service
from app.db import get_db
from app.schemas import APIModel

router = APIRouter(tags=["accounting"])

_XLSX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)
_XLSX_FILENAME = "Bens_e_Direitos.xlsx"


class MissingCnpjItem(APIModel):
    """An asset whose CNPJ is missing from the catalog."""

    Produto: str
    Grupo: str


class BensEDireitosResponse(APIModel):
    """Preview payload: the asset rows plus the missing-CNPJ list.

    ``assets`` are the raw dicts ``core`` produces (Portuguese keys, e.g.
    ``"Situação final"``, ``"Juros Sobre Capital Próprio"``) and are passed through
    unchanged so the response matches the legacy output exactly.
    """

    assets: list[dict[str, Any]]
    missing_cnpj: list[MissingCnpjItem]


class CnpjOverrideIn(APIModel):
    """One CNPJ override row (POST body item)."""

    Ticker: str
    Tipo: str | None = None
    CNPJ: str


class CnpjOverrideResult(APIModel):
    """Result of saving CNPJ overrides."""

    saved: int


@router.get("/accounting/bens-e-direitos", response_model=BensEDireitosResponse)
def bens_e_direitos(db: Session = Depends(get_db)) -> BensEDireitosResponse:
    """Build the Bens e Direitos preview from the imported data."""
    assets = service.build_assets(db)
    return BensEDireitosResponse(
        assets=assets,
        missing_cnpj=service.missing_cnpj(assets),
    )


@router.get("/accounting/bens-e-direitos.xlsx")
def bens_e_direitos_xlsx(db: Session = Depends(get_db)) -> StreamingResponse:
    """Stream the Bens e Direitos sheet as an ``.xlsx`` download."""
    assets = service.build_assets(db)
    content = service.build_xlsx(assets)
    return StreamingResponse(
        BytesIO(content),
        media_type=_XLSX_MEDIA_TYPE,
        headers={
            "Content-Disposition": f'attachment; filename="{_XLSX_FILENAME}"'
        },
    )


@router.post("/accounting/cnpj-overrides", response_model=CnpjOverrideResult)
def save_cnpj_overrides(rows: list[CnpjOverrideIn]) -> CnpjOverrideResult:
    """Persist CNPJ overrides via ``core.save_overrides`` and return the count saved.

    Overrides live in the legacy xlsx (not the DB), so this handler needs no session.
    """
    saved = service.save_cnpj([r.model_dump() for r in rows])
    return CnpjOverrideResult(saved=saved)
