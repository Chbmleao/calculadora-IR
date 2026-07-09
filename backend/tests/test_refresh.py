"""Unit tests for auto-update & refresh (task 13).

Self-contained: an isolated in-memory SQLite DB per test and deterministic fake /
counting quote services (no network). We never construct the FastAPI app or a
TestClient (sibling feature layers may be mid-write); the job logic is exercised
through ``refresh.run_daily`` / ``snapshot_today`` / ``refresh_quotes`` and the
importable ``jobs.scheduler`` directly.

Covers the acceptance criteria:
- a ``run_daily`` refreshes quotes and writes exactly one snapshot per day,
- ``snapshot_today`` is idempotent per date (re-run updates, never duplicates),
- request volume stays within free-tier limits (reads hit the cache; refresh is a
  single forced fetch),
- scheduler wiring is smoke-tested (the ``run_daily`` job is registered).
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.jobs.refresh import refresh_quotes, run_daily, snapshot_today
from app.jobs.scheduler import (
    JOB_ID,
    create_scheduler,
    get_scheduler,
    next_run_time,
    shutdown_scheduler,
    start_scheduler,
)
from app.models import Base, PositionSummary, Provento, Snapshot, Transaction
from app.portfolio.positions import build_positions
from app.quotes import cache
from app.quotes.base import DailyClose, Quote
from app.quotes.cache import CacheRow
from app.quotes.service import QuoteService

TODAY = date.today()


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


# --------------------------------------------------------------------------- #
# Test doubles                                                                 #
# --------------------------------------------------------------------------- #


class FakeQuoteService:
    """Implements the tiny surface the job layer needs: latest / refresh_latest / history."""

    def __init__(self, latest: dict[str, Decimal], closes: dict[str, Decimal]):
        self._latest = latest
        self._closes = closes
        self.refresh_calls = 0
        self.latest_calls = 0
        self.history_calls: list[tuple[str, date, date]] = []

    def latest(self, tickers):
        self.latest_calls += 1
        return {
            t: Quote(price=self._latest[t], date=TODAY, source="fake")
            for t in tickers
            if t in self._latest
        }

    def refresh_latest(self, tickers):
        self.refresh_calls += 1
        return {
            t: Quote(price=self._latest[t], date=TODAY, source="fake")
            for t in tickers
            if t in self._latest
        }

    def history(self, ticker, start, end):
        self.history_calls.append((ticker, start, end))
        close = self._closes.get(ticker)
        if close is None:
            return []
        days = (end - start).days
        return [DailyClose(start + timedelta(days=i), close) for i in range(days + 1)]


class CountingProvider:
    """Real ``QuoteProvider`` stand-in that counts network calls."""

    def __init__(self, name: str, closes: dict[str, Decimal]):
        self.name = name
        self._closes = closes
        self.latest_calls = 0
        self.history_calls = 0

    def latest(self, tickers):
        self.latest_calls += 1
        return {
            t: Quote(price=self._closes[t], date=TODAY, source=self.name)
            for t in tickers
            if t in self._closes
        }

    def history(self, ticker, start, end):
        self.history_calls += 1
        close = self._closes.get(ticker)
        if close is None:
            return []
        days = (end - start).days
        return [DailyClose(start + timedelta(days=i), close) for i in range(days + 1)]


def _seed_portfolio(db):
    """One held ticker (PETR4): a summary baseline + the matching buy + a provento."""
    db.add(
        PositionSummary(
            ticker="PETR4",
            qty_net=Decimal("100"),
            avg_price_buy=Decimal("30"),
            period_end=TODAY - timedelta(days=40),
        )
    )
    db.add(
        Transaction(
            trade_date=TODAY - timedelta(days=30),
            ticker="PETR4",
            market="a_vista",
            side="buy",
            quantity=Decimal("100"),
            price=Decimal("30"),
            value=Decimal("3000"),
        )
    )
    db.add(
        Provento(
            ticker="PETR4",
            pay_date=TODAY - timedelta(days=20),
            event_type="dividend",
            net_value=Decimal("50"),
        )
    )
    db.commit()


def _fake_service():
    # Live latest price 35 (positions), historical close 35 (evolution).
    return FakeQuoteService(latest={"PETR4": Decimal("35")}, closes={"PETR4": Decimal("35")})


# --------------------------------------------------------------------------- #
# snapshot_today                                                               #
# --------------------------------------------------------------------------- #


def test_snapshot_today_computes_expected_values(db):
    _seed_portfolio(db)
    snap = snapshot_today(db, quote_service=_fake_service())

    assert snap.date == TODAY
    assert snap.total_value == Decimal("3500.00")  # 100 @ live 35
    assert snap.total_cost == Decimal("3000.00")  # 100 @ avg 30
    assert snap.contributions_to_date == Decimal("3000.00")  # net buys (evolution)
    assert snap.cumulative_proventos == Decimal("50.00")


def test_snapshot_today_idempotent_per_day(db):
    _seed_portfolio(db)

    snapshot_today(db, quote_service=_fake_service())
    first_computed = db.get(Snapshot, TODAY).computed_at

    snapshot_today(db, quote_service=_fake_service())

    # Exactly one row for today, no matter how many times we run.
    count_today = db.execute(
        select(func.count()).select_from(Snapshot).where(Snapshot.date == TODAY)
    ).scalar_one()
    assert count_today == 1

    snap = db.get(Snapshot, TODAY)
    assert snap.total_value == Decimal("3500.00")
    # Re-run refreshes computed_at (an update, not an insert).
    assert snap.computed_at >= first_computed


def test_snapshot_today_upserts_existing_row(db):
    _seed_portfolio(db)
    # Pre-existing stale snapshot for today.
    db.add(
        Snapshot(
            date=TODAY,
            total_value=Decimal("1.00"),
            total_cost=Decimal("1.00"),
            contributions_to_date=Decimal("1.00"),
            cumulative_proventos=Decimal("1.00"),
        )
    )
    db.commit()

    snapshot_today(db, quote_service=_fake_service())

    count_today = db.execute(
        select(func.count()).select_from(Snapshot).where(Snapshot.date == TODAY)
    ).scalar_one()
    assert count_today == 1
    assert db.get(Snapshot, TODAY).total_value == Decimal("3500.00")


def test_snapshot_today_no_data_is_safe(db):
    # No positions, no transactions -> a zeroed, still-idempotent snapshot.
    snap = snapshot_today(db, quote_service=_fake_service())
    assert snap.date == TODAY
    assert snap.total_value == Decimal("0")
    assert snap.contributions_to_date == Decimal("0")


# --------------------------------------------------------------------------- #
# run_daily                                                                    #
# --------------------------------------------------------------------------- #


def test_run_daily_refreshes_quotes_and_writes_one_snapshot(db):
    _seed_portfolio(db)
    service = _fake_service()

    result = run_daily(db, quote_service=service)

    assert service.refresh_calls == 1  # exactly one forced refresh
    assert result.quotes_updated == 1
    assert result.snapshot.date == TODAY

    count_today = db.execute(
        select(func.count()).select_from(Snapshot).where(Snapshot.date == TODAY)
    ).scalar_one()
    assert count_today == 1


def test_run_daily_twice_same_day_keeps_one_snapshot(db):
    _seed_portfolio(db)

    run_daily(db, quote_service=_fake_service())
    run_daily(db, quote_service=_fake_service())

    count_today = db.execute(
        select(func.count()).select_from(Snapshot).where(Snapshot.date == TODAY)
    ).scalar_one()
    assert count_today == 1


def test_refresh_quotes_forces_single_fetch(db):
    _seed_portfolio(db)
    service = _fake_service()

    updated = refresh_quotes(db, quote_service=service)

    assert service.refresh_calls == 1
    assert set(updated) == {"PETR4"}


# --------------------------------------------------------------------------- #
# Free-tier / cache-hit behaviour                                             #
# --------------------------------------------------------------------------- #


def test_reads_hit_cache_within_ttl(db):
    """A fresh cache row means positions read with ZERO provider calls (free-tier safe)."""
    db.add(PositionSummary(ticker="PETR4", qty_net=Decimal("100"), avg_price_buy=Decimal("30")))
    db.commit()
    # Seed a fresh cached quote (fetched_at = now).
    cache.upsert(db, [CacheRow(ticker="PETR4", date=TODAY, close=Decimal("35"), source="seed")])

    brapi = CountingProvider("brapi", {"PETR4": Decimal("35")})
    yfin = CountingProvider("yfinance", {"PETR4": Decimal("35")})
    service = QuoteService(db, brapi=brapi, yfinance=yfin)

    # Cache-first read: the provider must not be touched.
    view = build_positions(db, service)
    assert view.totals.market_value == 3500.0
    assert brapi.latest_calls == 0
    assert yfin.latest_calls == 0

    # A forced refresh is exactly one batched provider call.
    refresh_quotes(db, quote_service=service)
    assert brapi.latest_calls == 1
    assert yfin.latest_calls == 0  # brapi resolved everything


# --------------------------------------------------------------------------- #
# Scheduler wiring (smoke)                                                     #
# --------------------------------------------------------------------------- #


def test_scheduler_registers_run_daily_job():
    scheduler = create_scheduler(interval_hours=6)
    job = scheduler.get_job(JOB_ID)
    assert job is not None
    assert job.id == JOB_ID
    # create_scheduler does not start anything, so the module exposes no next run.
    assert next_run_time() is None
    assert get_scheduler() is None


def test_start_and_shutdown_scheduler_lifecycle():
    scheduler = start_scheduler(interval_hours=6)
    try:
        assert scheduler.running
        assert get_scheduler() is scheduler
        assert next_run_time() is not None
        # Idempotent: starting again returns the same running scheduler.
        assert start_scheduler() is scheduler
    finally:
        shutdown_scheduler()

    assert get_scheduler() is None
    assert next_run_time() is None
