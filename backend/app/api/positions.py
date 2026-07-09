"""Portfolio positions endpoint (task 04), auto-mounted under ``/api``.

- ``GET /api/portfolio/positions`` -> :class:`PortfolioView`: per-ticker value,
  weight %, P/L, accumulated proventos, plus totals and an asset-class allocation
  breakdown. When nothing has been imported it returns an empty view carrying a
  ``message`` (never a 500).

This module is auto-discovered by ``app.api.register_routers``; it never edits any
shared wiring.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.portfolio.positions import PortfolioView, build_positions

router = APIRouter(tags=["portfolio"])


@router.get("/portfolio/positions", response_model=PortfolioView)
def portfolio_positions(db: Session = Depends(get_db)) -> PortfolioView:
    return build_positions(db)
