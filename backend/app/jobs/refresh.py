"""Refresh & daily-snapshot service (task 13).

Three small orchestrators that keep the dashboard fresh without any manual steps,
composed entirely from existing layers (never re-implementing quote/positions/
evolution logic):

- :func:`refresh_quotes` — force a network refresh of every held ticker's latest
  price via the task-03 quote service (``refresh_latest``), populating ``quote_cache``.
- :func:`snapshot_today` — compute today's portfolio market value (task-04
  ``build_positions``) plus cumulative contributions/proventos (task-05 evolution)
  and **upsert one row per date** into ``snapshots`` (idempotent).
- :func:`run_daily` — ``refresh_quotes`` then ``snapshot_today``, reusing a single
  :class:`QuoteService` so the refresh warms the cache that positions/evolution then
  read cache-first (keeping request volume within brapi's free tier).

None of these edit shared wiring; they are invoked from ``POST /api/jobs/run-daily``
(cron-style MVP) and from the importable APScheduler job in ``app.jobs.scheduler``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as _date, datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import Snapshot
from app.portfolio.evolution import EvolutionSeries, get_evolution_series
from app.portfolio.positions import PortfolioView, build_positions
from app.quotes.base import Quote, to_money
from app.quotes.service import QuoteService, get_portfolio_tickers

_ZERO = Decimal("0")


def _now_utc_naive() -> datetime:
    """Current UTC as a naive datetime (SQLite stores/returns naive UTC).

    Matches the convention used by ``evolution`` / ``quotes.cache`` so a snapshot's
    ``computed_at`` compares correctly against import timestamps in the cache-freshness
    check.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


@dataclass
class RunResult:
    """Outcome of a :func:`run_daily` pass."""

    quotes_updated: int
    snapshot: Snapshot


def refresh_quotes(db: Session, *, quote_service: object | None = None) -> dict[str, Quote]:
    """Force-refresh the latest price of every held ticker (task 03).

    Delegates to ``QuoteService.refresh_latest`` so the cache is written with fresh
    ``fetched_at`` stamps (which drives the ``last_quote_refresh`` surfaced by the
    status endpoint). ``quote_service`` is injectable for tests.
    """
    service = quote_service or QuoteService(db)
    tickers = get_portfolio_tickers(db)
    return service.refresh_latest(tickers)


def _final_point(series: EvolutionSeries, on_date: _date):
    """The latest daily point at/or before ``on_date`` (``None`` when the series is empty)."""
    for point in reversed(series.points):
        if point.date <= on_date:
            return point
    return None


def snapshot_today(
    db: Session,
    *,
    quote_service: object | None = None,
    on_date: _date | None = None,
) -> Snapshot:
    """Compute and upsert today's portfolio snapshot — idempotent per date.

    Market value / invested cost / cumulative proventos come from the live
    positions view (task 04, latest quotes); cumulative net contributions come from
    the evolution series' final point (task 05), which ``build_positions`` does not
    provide. When no positions have been imported yet the market-value fields fall
    back to the evolution reconstruction so a transactions-only dataset still yields a
    meaningful snapshot.

    The row is keyed on ``date`` (Snapshot PK), so a repeat call the same day
    **updates** the existing row instead of inserting a duplicate.
    """
    today = on_date or _date.today()

    series = get_evolution_series(db, quote_service=quote_service, to=today)
    view: PortfolioView = build_positions(db, quote_service)
    point = _final_point(series, today)

    contributions = point.contributions if point is not None else _ZERO

    if view.positions:
        total_value = to_money(view.totals.market_value)
        total_cost = to_money(view.totals.invested)
        proventos = point.proventos if point is not None else to_money(view.totals.proventos)
    elif point is not None:
        total_value = point.market_value
        total_cost = point.invested_cost
        proventos = point.proventos
    else:
        total_value = _ZERO
        total_cost = _ZERO
        proventos = _ZERO

    snap = db.get(Snapshot, today)
    if snap is None:
        snap = Snapshot(date=today)
        db.add(snap)
    snap.total_value = total_value
    snap.total_cost = total_cost
    snap.contributions_to_date = contributions
    snap.cumulative_proventos = proventos
    snap.computed_at = _now_utc_naive()

    db.commit()
    db.refresh(snap)
    return snap


def run_daily(db: Session, *, quote_service: object | None = None) -> RunResult:
    """Refresh quotes, then append/update today's snapshot (the daily job body).

    A single :class:`QuoteService` is shared across the refresh and the snapshot so
    the forced refresh warms the cache that ``build_positions`` (latest) and the
    evolution reconstruction (history) then read cache-first — one network burst per
    run, keeping volume within the providers' free tiers.
    """
    service = quote_service or QuoteService(db)
    quotes = refresh_quotes(db, quote_service=service)
    snapshot = snapshot_today(db, quote_service=service)
    return RunResult(quotes_updated=len(quotes), snapshot=snapshot)
