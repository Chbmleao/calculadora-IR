"""Target-allocation endpoints (task 06), auto-mounted under ``/api``.

- ``GET  /api/targets`` -> current desired weights (class-level and/or ticker-level),
  seeded from the ``.env`` ``TARGET_ALLOCATIONS`` JSON on first access if the table is
  empty. Groups that do not sum to ~100% come back with a ``warnings`` entry.
- ``PUT  /api/targets`` -> replace all stored targets with the supplied set (validated;
  off-100 sums warn but never hard-fail).

Auto-discovered by ``app.api.register_routers``; edits no shared wiring.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.portfolio.rebalance import (
    TargetsResponse,
    TargetsUpdate,
    load_targets,
    replace_targets,
    seed_targets_if_empty,
)

router = APIRouter(tags=["targets"])


@router.get("/targets", response_model=TargetsResponse)
def get_targets(db: Session = Depends(get_db)) -> TargetsResponse:
    seed_targets_if_empty(db)
    return load_targets(db)


@router.put("/targets", response_model=TargetsResponse)
def put_targets(payload: TargetsUpdate, db: Session = Depends(get_db)) -> TargetsResponse:
    return replace_targets(db, payload)
