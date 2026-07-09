"""Unit tests for patrimony evolution & rentability (task 05).

Self-contained: an isolated in-memory SQLite DB per test, a deterministic fake quote
service (no network), and synthetic transactions/proventos. We never construct the
FastAPI app/TestClient (sibling feature layers may be mid-write); the endpoint's
domain logic is exercised through ``get_evolution_series`` + ``compute_metrics``
directly.

Covers the acceptance criteria:
- dated series of patrimony/contributions/proventos from first trade → today,
- adding cash does NOT inflate TWR (contributions separated from market gains),
- reconstructed holdings on a past date match a hand-checked example,
- repeat calls served from the snapshot cache; recompute after a new import,
- granularity down-sampling (daily/weekly/monthly).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.models import Base, Provento, Snapshot, Transaction
from app.portfolio.evolution import (
    DailyPoint,
    compute_daily_series,
    downsample,
    forward_filled_prices,
    get_evolution_series,
    holdings_as_of,
)
from app.portfolio.returns import (
    absolute_gain,
    build_cashflows,
    compute_metrics,
    simple_return,
    time_weighted_return,
    xirr,
)
from app.quotes.base import DailyClose

_INPUT_DIR = Path(__file__).resolve().parents[2] / "input"
_HISTORICO = _INPUT_DIR / "negociacao-2026-05-24-12-24-22.xlsx"


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
# Test doubles / helpers                                                       #
# --------------------------------------------------------------------------- #


@dataclass
class Txn:
    """Lightweight transaction stand-in for the pure functions."""

    trade_date: date
    ticker: str
    side: str
    quantity: Decimal
    value: Decimal


@dataclass
class Prov:
    pay_date: date
    net_value: Decimal


class FakeQuoteService:
    """Returns a fixed close for every day in range; records history() calls."""

    def __init__(self, close_by_ticker: dict[str, Decimal]):
        self._close = close_by_ticker
        self.history_calls: list[tuple[str, date, date]] = []

    def history(self, ticker, start, end):
        self.history_calls.append((ticker, start, end))
        close = self._close.get(ticker)
        if close is None:
            return []
        days = (end - start).days
        return [DailyClose(start + timedelta(days=i), Decimal(close)) for i in range(days + 1)]


class SeriesQuoteService:
    """Serves a per-ticker {date: close} map (sparse); records history() calls."""

    def __init__(self, series: dict[str, dict[date, Decimal]]):
        self._series = series
        self.history_calls: list[tuple[str, date, date]] = []

    def history(self, ticker, start, end):
        self.history_calls.append((ticker, start, end))
        rows = self._series.get(ticker, {})
        return [DailyClose(d, Decimal(c)) for d, c in sorted(rows.items()) if start <= d <= end]


def _add_txn(db, trade_date, ticker, side, quantity, value, imported_at=None):
    t = Transaction(
        trade_date=trade_date,
        ticker=ticker,
        market="a_vista",
        side=side,
        quantity=Decimal(str(quantity)),
        price=Decimal("1"),
        value=Decimal(str(value)),
    )
    if imported_at is not None:
        t.imported_at = imported_at
    db.add(t)
    return t


# --------------------------------------------------------------------------- #
# Holdings reconstruction                                                      #
# --------------------------------------------------------------------------- #


def test_holdings_as_of_hand_checked():
    txns = [
        Txn(date(2024, 1, 2), "PETR4", "buy", Decimal("100"), Decimal("3000")),
        Txn(date(2024, 1, 10), "MXRF11", "buy", Decimal("50"), Decimal("500")),
        Txn(date(2024, 1, 20), "PETR4", "buy", Decimal("50"), Decimal("1600")),
        Txn(date(2024, 2, 1), "PETR4", "sell", Decimal("30"), Decimal("1050")),
    ]
    # Before any trade.
    assert holdings_as_of(txns, date(2024, 1, 1)) == {}
    # After first buy only.
    assert holdings_as_of(txns, date(2024, 1, 2)) == {"PETR4": Decimal("100")}
    # Mid-January: PETR4 100 + MXRF11 50 (second PETR4 buy not yet).
    assert holdings_as_of(txns, date(2024, 1, 15)) == {
        "PETR4": Decimal("100"),
        "MXRF11": Decimal("50"),
    }
    # After the second buy: 150 PETR4.
    assert holdings_as_of(txns, date(2024, 1, 25)) == {
        "PETR4": Decimal("150"),
        "MXRF11": Decimal("50"),
    }
    # After the sell: 120 PETR4.
    assert holdings_as_of(txns, date(2024, 2, 5)) == {
        "PETR4": Decimal("120"),
        "MXRF11": Decimal("50"),
    }


def test_holdings_drops_zeroed_positions():
    txns = [
        Txn(date(2024, 1, 2), "PETR4", "buy", Decimal("100"), Decimal("3000")),
        Txn(date(2024, 1, 3), "PETR4", "sell", Decimal("100"), Decimal("3100")),
    ]
    assert holdings_as_of(txns, date(2024, 1, 5)) == {}


# --------------------------------------------------------------------------- #
# Forward fill                                                                 #
# --------------------------------------------------------------------------- #


def test_forward_fill_carries_last_close_over_gaps():
    rows = [
        DailyClose(date(2024, 1, 2), Decimal("10.00")),
        DailyClose(date(2024, 1, 5), Decimal("11.00")),
    ]
    dense = forward_filled_prices(rows, date(2024, 1, 1), date(2024, 1, 7))
    # No price before the first close.
    assert date(2024, 1, 1) not in dense
    assert dense[date(2024, 1, 2)] == Decimal("10.00")
    # Jan 3-4 carry Jan 2's close.
    assert dense[date(2024, 1, 3)] == Decimal("10.00")
    assert dense[date(2024, 1, 4)] == Decimal("10.00")
    assert dense[date(2024, 1, 5)] == Decimal("11.00")
    # Jan 6-7 carry Jan 5's close.
    assert dense[date(2024, 1, 7)] == Decimal("11.00")


# --------------------------------------------------------------------------- #
# Daily valuation                                                              #
# --------------------------------------------------------------------------- #


def test_daily_series_values_holdings_at_close():
    txns = [Txn(date(2024, 1, 2), "PETR4", "buy", Decimal("100"), Decimal("3000"))]
    prices = {"PETR4": {date(2024, 1, 2): Decimal("30"), date(2024, 1, 3): Decimal("32")}}
    points, unpriced = compute_daily_series(txns, [], prices, date(2024, 1, 2), date(2024, 1, 3))
    assert unpriced == []
    assert [p.date for p in points] == [date(2024, 1, 2), date(2024, 1, 3)]
    assert points[0].market_value == Decimal("3000.00")
    assert points[0].contributions == Decimal("3000.00")
    assert points[0].invested_cost == Decimal("3000.00")
    assert points[0].flow == Decimal("3000.00")
    # Day 2: 100 * 32 = 3200 market value, cost basis unchanged, no new flow.
    assert points[1].market_value == Decimal("3200.00")
    assert points[1].invested_cost == Decimal("3000.00")
    assert points[1].flow == Decimal("0.00")


def test_daily_series_accumulates_proventos():
    txns = [Txn(date(2024, 1, 2), "PETR4", "buy", Decimal("100"), Decimal("3000"))]
    prices = {"PETR4": {date(2024, 1, 2): Decimal("30")}}
    provs = [Prov(date(2024, 1, 3), Decimal("12.34")), Prov(date(2024, 1, 4), Decimal("5.66"))]
    points, _ = compute_daily_series(txns, provs, prices, date(2024, 1, 2), date(2024, 1, 5))
    assert points[0].proventos == Decimal("0.00")  # before pay date
    assert points[1].proventos == Decimal("12.34")
    assert points[2].proventos == Decimal("18.00")  # cumulative
    assert points[3].proventos == Decimal("18.00")


def test_daily_series_unpriced_holding_valued_at_cost_and_flagged():
    txns = [Txn(date(2024, 1, 2), "NEW3", "buy", Decimal("10"), Decimal("100"))]
    # Price only appears on Jan 4.
    prices = {"NEW3": {date(2024, 1, 4): Decimal("15")}}
    points, unpriced = compute_daily_series(txns, [], prices, date(2024, 1, 2), date(2024, 1, 4))
    assert unpriced == ["NEW3"]
    # Jan 2-3: valued at cost basis 100.
    assert points[0].market_value == Decimal("100.00")
    assert points[1].market_value == Decimal("100.00")
    # Jan 4: priced -> 10 * 15 = 150.
    assert points[2].market_value == Decimal("150.00")


def test_sell_reduces_cost_basis_at_average():
    txns = [
        Txn(date(2024, 1, 2), "PETR4", "buy", Decimal("100"), Decimal("3000")),  # avg 30
        Txn(date(2024, 1, 5), "PETR4", "sell", Decimal("40"), Decimal("1600")),  # sell 40 @ 40
    ]
    prices = {"PETR4": {date(2024, 1, 2): Decimal("30"), date(2024, 1, 5): Decimal("40")}}
    points, _ = compute_daily_series(txns, [], prices, date(2024, 1, 2), date(2024, 1, 5))
    last = points[-1]
    # 60 shares left, cost basis 60 * 30 = 1800; contributions net = 3000 - 1600 = 1400.
    assert last.invested_cost == Decimal("1800.00")
    assert last.contributions == Decimal("1400.00")
    assert last.market_value == Decimal("2400.00")  # 60 * 40


# --------------------------------------------------------------------------- #
# Return metrics                                                               #
# --------------------------------------------------------------------------- #


def test_twr_ignores_contributions_flat_prices():
    """Pure contributions with flat prices -> ~0% TWR but rising market value."""
    txns = [
        Txn(date(2024, 1, 1), "PETR4", "buy", Decimal("100"), Decimal("1000")),
        Txn(date(2024, 1, 2), "PETR4", "buy", Decimal("100"), Decimal("1000")),
        Txn(date(2024, 1, 3), "PETR4", "buy", Decimal("100"), Decimal("1000")),
    ]
    prices = {"PETR4": {d: Decimal("10") for d in [date(2024, 1, i) for i in range(1, 4)]}}
    points, _ = compute_daily_series(txns, [], prices, date(2024, 1, 1), date(2024, 1, 3))
    # Market value climbs with contributions...
    assert [p.market_value for p in points] == [
        Decimal("1000.00"),
        Decimal("2000.00"),
        Decimal("3000.00"),
    ]
    # ...but TWR stays flat.
    assert time_weighted_return(points) == 0.0
    # Simple return, by contrast, is 0 here too (no market move), sanity check.
    last = points[-1]
    assert simple_return(last.market_value, last.proventos, last.contributions) == 0.0


def test_twr_equals_price_change_no_flows():
    """A price rise with no flows -> TWR = the price change %."""
    txns = [Txn(date(2024, 1, 1), "PETR4", "buy", Decimal("100"), Decimal("1000"))]
    prices = {
        "PETR4": {
            date(2024, 1, 1): Decimal("10"),
            date(2024, 1, 2): Decimal("11"),
            date(2024, 1, 3): Decimal("12"),
        }
    }
    points, _ = compute_daily_series(txns, [], prices, date(2024, 1, 1), date(2024, 1, 3))
    # 10 -> 12 is +20%.
    assert time_weighted_return(points) == pytest.approx(0.2)


def test_simple_return_and_absolute_gain():
    mv, prov, contrib = Decimal("1200"), Decimal("50"), Decimal("1000")
    # (1200 + 50 - 1000) / 1000 = 0.25
    assert simple_return(mv, prov, contrib) == 0.25
    assert absolute_gain(mv, prov, contrib) == Decimal("250.00")
    # No money in -> undefined.
    assert simple_return(Decimal("100"), Decimal("0"), Decimal("0")) is None


def test_xirr_recovers_known_rate():
    # Invest 1000 today, worth 1100 exactly one year later -> ~10% annualized.
    flows = [(date(2024, 1, 1), Decimal("-1000")), (date(2025, 1, 1), Decimal("1100"))]
    rate = xirr(flows)
    assert rate is not None
    assert rate == pytest.approx(0.10, abs=1e-3)


def test_xirr_none_when_degenerate():
    assert xirr([(date(2024, 1, 1), Decimal("-1000"))]) is None  # single flow
    # All same sign -> no root.
    assert xirr([(date(2024, 1, 1), Decimal("-1000")), (date(2025, 1, 1), Decimal("-5"))]) is None


def test_build_cashflows_shape():
    points = [
        DailyPoint(date(2024, 1, 1), Decimal("1000"), Decimal("1000"), Decimal("0"), Decimal("1000"), Decimal("1000")),
        DailyPoint(date(2024, 1, 2), Decimal("1010"), Decimal("1000"), Decimal("5"), Decimal("1000"), Decimal("0")),
    ]
    flows = build_cashflows(points)
    # Day 1: -1000 outflow. Day 2: +5 provento inflow. Final: +1010 value.
    assert (date(2024, 1, 1), Decimal("-1000")) in flows
    assert (date(2024, 1, 2), Decimal("5")) in flows
    assert flows[-1] == (date(2024, 1, 2), Decimal("1010"))


def test_compute_metrics_empty_series():
    m = compute_metrics([])
    assert m == {"simple_return": None, "twr": None, "xirr": None, "absolute_gain": 0.0}


# --------------------------------------------------------------------------- #
# Granularity down-sampling                                                    #
# --------------------------------------------------------------------------- #


def _flat_point(d: date) -> DailyPoint:
    return DailyPoint(d, Decimal("1"), Decimal("1"), Decimal("0"), Decimal("1"), Decimal("0"))


def test_downsample_weekly_and_monthly():
    days = [date(2024, 1, 1) + timedelta(days=i) for i in range(40)]  # Jan 1 .. Feb 9
    points = [_flat_point(d) for d in days]

    assert downsample(points, "daily") == points

    weekly = downsample(points, "weekly")
    # Each kept point is the last day of its ISO week (except the final partial week).
    for i, p in enumerate(weekly):
        is_last = i == len(weekly) - 1
        # Sunday is ISO weekday 7 -> last of the week, or the final point.
        assert p.date.isoweekday() == 7 or is_last
    assert weekly[-1].date == days[-1]

    monthly = downsample(points, "monthly")
    assert [p.date for p in monthly] == [date(2024, 1, 31), days[-1]]


# --------------------------------------------------------------------------- #
# Orchestration + snapshot cache (DB-backed)                                   #
# --------------------------------------------------------------------------- #


def test_get_evolution_series_reconstructs_and_caches(db):
    _add_txn(db, date.today() - timedelta(days=3), "PETR4", "buy", 100, 3000)
    db.commit()

    quotes = FakeQuoteService({"PETR4": Decimal("30")})
    series = get_evolution_series(db, quote_service=quotes, to=date.today())

    assert series.from_cache is False
    assert series.as_of == date.today()
    assert series.points[0].date == date.today() - timedelta(days=3)
    assert series.points[-1].date == date.today()
    assert series.points[-1].market_value == Decimal("3000.00")  # 100 * 30
    assert quotes.history_calls  # provider was consulted
    # Snapshots persisted, one per day.
    assert db.execute(select(Snapshot)).all()

    # Second call: fresh cache covering today -> served from snapshots, no quotes.
    quotes2 = FakeQuoteService({"PETR4": Decimal("30")})
    cached = get_evolution_series(db, quote_service=quotes2, to=date.today())
    assert cached.from_cache is True
    assert quotes2.history_calls == []  # cache hit -> no provider lookup
    assert [p.date for p in cached.points] == [p.date for p in series.points]
    assert cached.points[-1].market_value == series.points[-1].market_value


def test_get_evolution_recomputes_after_new_import(db):
    _add_txn(db, date.today() - timedelta(days=3), "PETR4", "buy", 100, 3000)
    db.commit()

    quotes = FakeQuoteService({"PETR4": Decimal("30"), "MXRF11": Decimal("10")})
    first = get_evolution_series(db, quote_service=quotes, to=date.today())
    assert first.points[-1].market_value == Decimal("3000.00")

    # A new import lands with a timestamp AFTER the snapshots were computed.
    later = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=1)
    _add_txn(db, date.today() - timedelta(days=2), "MXRF11", "buy", 50, 500, imported_at=later)
    db.commit()

    quotes2 = FakeQuoteService({"PETR4": Decimal("30"), "MXRF11": Decimal("10")})
    updated = get_evolution_series(db, quote_service=quotes2, to=date.today())
    assert updated.from_cache is False  # stale cache -> recompute
    assert quotes2.history_calls  # provider consulted again
    # 100*30 + 50*10 = 3500.
    assert updated.points[-1].market_value == Decimal("3500.00")


def test_twr_not_inflated_end_to_end(db):
    """Two equal contributions at a flat price -> endpoint metrics show ~0% TWR."""
    day0 = date.today() - timedelta(days=2)
    day1 = date.today() - timedelta(days=1)
    _add_txn(db, day0, "PETR4", "buy", 100, 1000)
    _add_txn(db, day1, "PETR4", "buy", 100, 1000)
    db.commit()

    quotes = SeriesQuoteService(
        {"PETR4": {day0: Decimal("10"), day1: Decimal("10"), date.today(): Decimal("10")}}
    )
    series = get_evolution_series(db, quote_service=quotes, to=date.today())
    metrics = compute_metrics(series.points)

    # Contributions doubled the patrimony but TWR is flat.
    assert series.points[-1].market_value == Decimal("2000.00")
    assert series.points[-1].contributions == Decimal("2000.00")
    assert metrics["twr"] == 0.0


def test_empty_portfolio_returns_empty(db):
    series = get_evolution_series(db, quote_service=FakeQuoteService({}), to=date.today())
    assert series.points == []
    assert compute_metrics(series.points)["absolute_gain"] == 0.0


# --------------------------------------------------------------------------- #
# Realistic B3 sample (skipped when the gitignored input file is absent)       #
# --------------------------------------------------------------------------- #


@pytest.mark.skipif(not _HISTORICO.exists(), reason="B3 histórico sample not present")
def test_real_historico_reconstruction(db):
    from app.ingestion.transactions import parse_transactions

    rows, _ = parse_transactions(_HISTORICO)
    for r in rows:
        db.add(Transaction(origin="import", **r))
    db.commit()

    tickers = sorted({r["ticker"] for r in rows})
    quotes = FakeQuoteService({t: Decimal("10") for t in tickers})
    series = get_evolution_series(db, quote_service=quotes, to=date.today())

    assert series.points, "expected a non-empty equity curve from the real sample"
    assert series.as_of == date.today()
    # Contributions are strictly positive once the first buy lands.
    assert series.points[-1].contributions > Decimal("0")
    # Metrics compute without error on real data.
    metrics = compute_metrics(series.points)
    assert metrics["absolute_gain"] is not None

    # Second call is served from cache.
    quotes2 = FakeQuoteService({t: Decimal("10") for t in tickers})
    cached = get_evolution_series(db, quote_service=quotes2, to=date.today())
    assert cached.from_cache is True
    assert quotes2.history_calls == []
