"""Rebalancing endpoint (task 06), auto-mounted under ``/api``.

- ``GET /api/portfolio/rebalance?contribution=<number>`` -> :class:`RebalancePlan`:
  per-key current vs target weight, drift, and suggested buys. ``contribution > 0``
  distributes a deposit via buys only (most-underweight first); ``contribution == 0``
  returns the full buy/sell plan to hit the targets.

Targets are seeded from ``.env`` on first access if the table is empty. Auto-discovered
by ``app.api.register_routers``; edits no shared wiring.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.portfolio.rebalance import RebalancePlan, build_rebalance, seed_targets_if_empty

router = APIRouter(tags=["portfolio"])


@router.get("/portfolio/rebalance", response_model=RebalancePlan)
def portfolio_rebalance(
    contribution: float = Query(0, ge=0, description="New deposit to allocate via buys."),
    db: Session = Depends(get_db),
) -> RebalancePlan:
    seed_targets_if_empty(db)
    return build_rebalance(db, contribution=contribution)
