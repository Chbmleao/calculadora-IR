"""Job endpoints (task 13), auto-mounted under ``/api``.

- ``POST /api/jobs/run-daily`` -> force a full refresh (latest quotes) + upsert
  today's portfolio snapshot; also the target an external cron hits.
- ``GET  /api/jobs/status``    -> freshness surface for the header (task 08):
  ``{last_quote_refresh, last_snapshot_date, next_run}``.

``POST /api/quotes/refresh`` (manual price-only refresh) already lives in the quotes
router (task 03) and is intentionally NOT redefined here. This module is
auto-discovered by ``app.api.register_routers`` and never edits shared wiring.
"""

from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.jobs.refresh import run_daily
from app.jobs.scheduler import next_run_time
from app.models import QuoteCache, Snapshot
from app.schemas import APIModel

router = APIRouter(tags=["jobs"])


class RunDailyResult(APIModel):
    """Outcome of a manual/cron ``run-daily`` trigger."""

    quotes_updated: int
    snapshot_date: date
    total_value: float | None
    contributions_to_date: float | None
    cumulative_proventos: float | None


class JobStatus(APIModel):
    """Freshness payload for the dashboard header."""

    last_quote_refresh: datetime | None
    last_snapshot_date: date | None
    next_run: datetime | None = None


def _as_float(value) -> float | None:
    return float(value) if value is not None else None


@router.post("/jobs/run-daily", response_model=RunDailyResult)
def run_daily_endpoint(db: Session = Depends(get_db)) -> RunDailyResult:
    result = run_daily(db)
    snap = result.snapshot
    return RunDailyResult(
        quotes_updated=result.quotes_updated,
        snapshot_date=snap.date,
        total_value=_as_float(snap.total_value),
        contributions_to_date=_as_float(snap.contributions_to_date),
        cumulative_proventos=_as_float(snap.cumulative_proventos),
    )


@router.get("/jobs/status", response_model=JobStatus)
def jobs_status(db: Session = Depends(get_db)) -> JobStatus:
    last_quote_refresh = db.execute(select(func.max(QuoteCache.fetched_at))).scalar_one_or_none()
    last_snapshot_date = db.execute(select(func.max(Snapshot.date))).scalar_one_or_none()
    return JobStatus(
        last_quote_refresh=last_quote_refresh,
        last_snapshot_date=last_snapshot_date,
        next_run=next_run_time(),
    )
