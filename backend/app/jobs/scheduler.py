"""APScheduler wiring for the daily refresh job (task 13) — importable, not auto-started.

This module only *builds* and optionally *runs* a ``BackgroundScheduler`` that fires
:func:`app.jobs.refresh.run_daily` on a fixed interval. It deliberately does **not**
touch ``app.main``: the MVP triggers the job cron-style via ``POST /api/jobs/run-daily``,
and the coordinator wires ``start_scheduler()``/``shutdown_scheduler()`` into the app's
startup/shutdown lifecycle later.

Design notes:
- The job body opens its **own** short-lived ``SessionLocal`` (the scheduler runs on a
  background thread with no request/``get_db`` context) and always closes it.
- ``snapshot_today`` is idempotent per date, so even if the interval fires several
  times a day at most one snapshot row per day is written — the "guard against
  duplicate same-day snapshots" the spec asks for.
- Interval is configurable via the ``JOB_INTERVAL_HOURS`` env var (documented here so
  it can live in ``.env``); default is every 12 hours. Kept well within brapi's
  ~15k/month free tier for a single portfolio thanks to the quote cache.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)

#: Stable id for the daily job so wiring/tests can look it up.
JOB_ID = "run_daily"

#: Default cadence when ``JOB_INTERVAL_HOURS`` is unset.
DEFAULT_INTERVAL_HOURS = 12

#: Process-wide scheduler once :func:`start_scheduler` has run (``None`` otherwise).
_scheduler: BackgroundScheduler | None = None


def _interval_hours(override: int | None = None) -> int:
    """Resolve the interval: explicit override → ``JOB_INTERVAL_HOURS`` env → default."""
    if override is not None:
        return override
    raw = os.environ.get("JOB_INTERVAL_HOURS")
    if raw:
        try:
            value = int(raw)
            if value > 0:
                return value
        except ValueError:
            logger.warning("invalid JOB_INTERVAL_HOURS=%r; using default", raw)
    return DEFAULT_INTERVAL_HOURS


def _run_daily_job() -> None:
    """Scheduler entry point: run the daily refresh on its own DB session."""
    from app.db import SessionLocal
    from app.jobs.refresh import run_daily

    db = SessionLocal()
    try:
        result = run_daily(db)
        logger.info(
            "run_daily job complete: %s quotes refreshed, snapshot for %s",
            result.quotes_updated,
            result.snapshot.date,
        )
    except Exception:  # pragma: no cover - defensive: never let the thread die silently
        logger.exception("run_daily job failed")
    finally:
        db.close()


def create_scheduler(interval_hours: int | None = None) -> BackgroundScheduler:
    """Build (but do not start) a scheduler with the ``run_daily`` job registered.

    Exposed separately so wiring/tests can assert the job is registered without
    starting a background thread.
    """
    hours = _interval_hours(interval_hours)
    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(
        _run_daily_job,
        trigger=IntervalTrigger(hours=hours),
        id=JOB_ID,
        name="Daily quote refresh + portfolio snapshot",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    return scheduler


def start_scheduler(interval_hours: int | None = None) -> BackgroundScheduler:
    """Start (idempotently) the process-wide scheduler and return it.

    The coordinator calls this from app startup. Calling it twice is a no-op that
    returns the already-running scheduler.
    """
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        return _scheduler
    _scheduler = create_scheduler(interval_hours)
    _scheduler.start()
    logger.info("run_daily scheduler started (every %sh)", _interval_hours(interval_hours))
    return _scheduler


def shutdown_scheduler(wait: bool = False) -> None:
    """Stop the process-wide scheduler if one is running (safe to call unconditionally)."""
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=wait)
    _scheduler = None


def get_scheduler() -> BackgroundScheduler | None:
    """Return the running scheduler, or ``None`` when none has been started."""
    return _scheduler


def next_run_time() -> datetime | None:
    """Next scheduled ``run_daily`` fire time, or ``None`` when no scheduler is running."""
    if _scheduler is None:
        return None
    job = _scheduler.get_job(JOB_ID)
    # ``next_run_time`` is only populated once the scheduler is running (the slot is
    # unset while a job is merely pending), so read it defensively.
    return getattr(job, "next_run_time", None) if job is not None else None
