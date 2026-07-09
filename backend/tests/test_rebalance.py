"""Unit tests for target allocation & rebalancing (task 06).

Exercise the domain layer directly against an isolated in-memory SQLite session with a
mocked quote service — no FastAPI app / TestClient (the app auto-imports sibling routers
that may be mid-write during a parallel wave).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.models import Base, PositionSummary, TargetAllocation
from app.portfolio.rebalance import (
    TargetInput,
    TargetsUpdate,
    build_rebalance,
    load_targets,
    replace_targets,
    seed_targets_if_empty,
)
from app.quotes.base import Quote


@pytest.fixture
def db() -> Session:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, future=True)
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, future=True)
    session = TestSession()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


class FakeQuoteService:
    """Minimal stand-in for QuoteService: returns preloaded latest quotes."""

    def __init__(self, prices: dict[str, Quote]):
        self._prices = prices

    def latest(self, tickers: list[str]) -> dict[str, Quote]:
        return {t: self._prices[t] for t in tickers if t in self._prices}


def _summary(ticker: str, qty: str, avg: str, period_end=date(2024, 12, 31)) -> PositionSummary:
    return PositionSummary(
        ticker=ticker, qty_net=Decimal(qty), avg_price_buy=Decimal(avg), period_end=period_end
    )


def _quote(price: str, on=date(2025, 1, 2)) -> Quote:
    return Quote(price=Decimal(price), date=on, source="test")


def _rows_by_key(plan):
    return {r.key: r for r in plan.rows}


# A portfolio worth 3,000: Ação 1,000 (target 40% -> want 1,600), FII 1,000 (30% -> 900),
# ETF 1,000 (20% -> 600), BDR 0 held. Prices chosen so shares are cleanly divisible.
def _seed_portfolio(db: Session) -> FakeQuoteService:
    db.add_all(
        [
            _summary("ITSA4", "100", "10"),  # Ação, price 10 -> mv 1000
            _summary("HGLG11", "10", "100"),  # FII,  price 100 -> mv 1000
            _summary("IVVB11", "10", "100"),  # ETF,  price 100 -> mv 1000
        ]
    )
    db.commit()
    return FakeQuoteService(
        {"ITSA4": _quote("10"), "HGLG11": _quote("100"), "IVVB11": _quote("100")}
    )


def _class_targets(db: Session) -> None:
    db.add_all(
        [
            TargetAllocation(kind="class", key="Ação", target_pct=Decimal("40")),
            TargetAllocation(kind="class", key="FII", target_pct=Decimal("30")),
            TargetAllocation(kind="class", key="ETF", target_pct=Decimal("20")),
            TargetAllocation(kind="class", key="BDR", target_pct=Decimal("10")),
        ]
    )
    db.commit()


# --------------------------------------------------------------------------- #
# Targets: read / replace / warnings                                          #
# --------------------------------------------------------------------------- #
def test_replace_and_read_targets(db):
    replace_targets(
        db,
        TargetsUpdate(
            class_targets=[
                TargetInput(key="Ação", target_pct=60),
                TargetInput(key="FII", target_pct=40),
            ],
            ticker_targets=[TargetInput(key="itsa4f", target_pct=100)],
        ),
    )
    resp = load_targets(db)
    cls = {t.key: t.target_pct for t in resp.class_targets}
    tkr = {t.key: t.target_pct for t in resp.ticker_targets}
    assert cls == {"Ação": 60.0, "FII": 40.0}
    assert tkr == {"ITSA4": 100.0}  # ticker canonicalized (trailing F stripped, upper)
    assert resp.warnings == []  # both groups sum to 100


def test_off_100_sum_warns_not_fails(db):
    resp = replace_targets(
        db,
        TargetsUpdate(
            class_targets=[
                TargetInput(key="Ação", target_pct=50),
                TargetInput(key="FII", target_pct=30),  # sums to 80
            ]
        ),
    )
    assert any("80" in w and "Class" in w for w in resp.warnings)
    # Still persisted despite the warning.
    assert {t.key for t in resp.class_targets} == {"Ação", "FII"}


def test_replace_wipes_previous_targets(db):
    replace_targets(db, TargetsUpdate(class_targets=[TargetInput(key="Ação", target_pct=100)]))
    replace_targets(db, TargetsUpdate(class_targets=[TargetInput(key="FII", target_pct=100)]))
    resp = load_targets(db)
    assert {t.key for t in resp.class_targets} == {"FII"}


# --------------------------------------------------------------------------- #
# Seeding                                                                      #
# --------------------------------------------------------------------------- #
def test_seed_from_env(monkeypatch, db):
    import app.portfolio.rebalance as rb

    monkeypatch.setattr(
        rb, "_seed_raw", lambda: '{"class": {"Ação": 40, "FII": 30, "ETF": 20, "BDR": 10}}'
    )
    warnings = seed_targets_if_empty(db)
    assert warnings == []  # sums to 100
    class_targets, _ = rb._load_target_dicts(db)
    assert class_targets == {
        "Ação": Decimal("40"),
        "FII": Decimal("30"),
        "ETF": Decimal("20"),
        "BDR": Decimal("10"),
    }


def test_seed_is_idempotent_and_skips_when_present(monkeypatch, db):
    import app.portfolio.rebalance as rb

    db.add(TargetAllocation(kind="class", key="Ação", target_pct=Decimal("100")))
    db.commit()
    monkeypatch.setattr(rb, "_seed_raw", lambda: '{"class": {"FII": 100}}')
    assert seed_targets_if_empty(db) == []  # table not empty -> no seed
    assert db.scalar(select(TargetAllocation.key).where(TargetAllocation.kind == "class")) == "Ação"


# --------------------------------------------------------------------------- #
# Rebalance — contribution mode                                               #
# --------------------------------------------------------------------------- #
def test_contribution_no_sells_and_totals_to_contribution(db):
    quotes = _seed_portfolio(db)
    _class_targets(db)
    plan = build_rebalance(db, contribution=1000, quote_service=quotes)

    assert plan.mode == "contribution"
    # (a) never suggests a sell.
    assert all(r.suggested_buy_amount >= 0 for r in plan.rows)
    # (c) buys + leftover ~= contribution (leftover only from indivisible shares).
    spent = sum(r.suggested_buy_amount for r in plan.rows)
    assert abs(spent + plan.leftover_cash - 1000) < 0.01
    assert plan.leftover_cash < 100  # at most ~one share of the priciest name


def test_contribution_goes_to_most_underweight_first(db):
    quotes = _seed_portfolio(db)
    _class_targets(db)
    # base = 3000 + 1000 = 4000. Deficits: Ação 40%*4000-1000=600 (most), FII 900-1000=-100
    # (overweight, no buy), ETF 800-1000=-200 (overweight), BDR 400-0=400.
    plan = build_rebalance(db, contribution=1000, quote_service=quotes)
    rows = _rows_by_key(plan)

    # The most-underweight held names get the money; overweight names get nothing.
    assert rows["ITSA4"].suggested_buy_amount > 0  # Ação, biggest gap
    assert rows["HGLG11"].suggested_buy_amount == 0  # FII overweight -> no buy
    assert rows["IVVB11"].suggested_buy_amount == 0  # ETF overweight -> no buy
    # Ação's gap (600) is filled before BDR's (400): Ação fully funded to target.
    assert rows["ITSA4"].suggested_buy_amount == 600.0  # 60 shares @ 10
    assert rows["ITSA4"].suggested_buy_qty == 60.0
    # BDR has no holdings -> surfaces as a class row, funded with the remaining 400.
    assert rows["BDR"].kind == "class"
    assert rows["BDR"].suggested_buy_amount == 400.0
    assert rows["BDR"].suggested_buy_qty is None  # no price to size shares


def test_contribution_whole_share_leftover(db):
    # One holding, target 100%, deposit not divisible by the R$30 share price.
    db.add(_summary("ITSA4", "10", "10"))  # mv = 10 * 30 = 300
    db.commit()
    quotes = FakeQuoteService({"ITSA4": _quote("30")})
    replace_targets(db, TargetsUpdate(ticker_targets=[TargetInput(key="ITSA4", target_pct=100)]))
    plan = build_rebalance(db, contribution=100, quote_service=quotes)
    row = _rows_by_key(plan)["ITSA4"]
    assert row.suggested_buy_qty == 3.0  # floor(100 / 30)
    assert row.suggested_buy_amount == 90.0
    assert plan.leftover_cash == 10.0  # 100 - 90, indivisible remainder


# --------------------------------------------------------------------------- #
# Rebalance — zero-contribution (full buy/sell) mode                          #
# --------------------------------------------------------------------------- #
def test_zero_contribution_full_plan_has_buys_and_sells(db):
    quotes = _seed_portfolio(db)
    _class_targets(db)
    plan = build_rebalance(db, contribution=0, quote_service=quotes)
    rows = _rows_by_key(plan)

    assert plan.mode == "rebalance"
    # base = total_mv = 3000. Targets: Ação 1200 (buy 200), FII 900 (sell 100),
    # ETF 600 (sell 400), BDR 300 (buy 300, class row).
    assert rows["ITSA4"].suggested_buy_amount == 200.0  # buy
    assert rows["HGLG11"].suggested_buy_amount == -100.0  # sell
    assert rows["IVVB11"].suggested_buy_amount == -400.0  # sell
    assert rows["BDR"].suggested_buy_amount == 300.0
    # Whole-share sizing (nearest): FII price 100 -> -1 share.
    assert rows["HGLG11"].suggested_buy_qty == -1.0
    assert rows["IVVB11"].suggested_buy_qty == -4.0


def test_drift_matches_current_weights(db):
    quotes = _seed_portfolio(db)
    _class_targets(db)
    plan = build_rebalance(db, contribution=0, quote_service=quotes)
    rows = _rows_by_key(plan)
    # Each held name is 1000/3000 = 33.33% of the portfolio.
    # drift_pct = current_pct - target_pct.
    assert rows["ITSA4"].current_pct == pytest.approx(33.33, abs=0.01)
    assert rows["ITSA4"].target_pct == 40.0
    assert rows["ITSA4"].drift_pct == pytest.approx(33.33 - 40.0, abs=0.01)
    assert rows["IVVB11"].drift_pct == pytest.approx(33.33 - 20.0, abs=0.01)


# --------------------------------------------------------------------------- #
# Ticker-level precedence over class split                                    #
# --------------------------------------------------------------------------- #
def test_ticker_target_overrides_class_split(db):
    quotes = _seed_portfolio(db)
    # Ação class target 40%, but an explicit ITSA4 ticker target of 55% must win.
    db.add(TargetAllocation(kind="class", key="Ação", target_pct=Decimal("40")))
    db.add(TargetAllocation(kind="ticker", key="ITSA4", target_pct=Decimal("55")))
    db.commit()
    plan = build_rebalance(db, contribution=0, quote_service=quotes)
    row = _rows_by_key(plan)["ITSA4"]
    assert row.kind == "ticker"
    assert row.target_pct == 55.0  # ticker-level target, not the class split


# --------------------------------------------------------------------------- #
# Empty portfolio never crashes                                               #
# --------------------------------------------------------------------------- #
def test_empty_portfolio_no_crash(db):
    _class_targets(db)
    plan = build_rebalance(db, contribution=1000, quote_service=FakeQuoteService({}))
    assert plan.total_market_value == 0.0
    # All classes are empty -> four class-level rows, no share quantities.
    assert {r.key for r in plan.rows} == {"Ação", "FII", "ETF", "BDR"}
    assert all(r.suggested_buy_qty is None for r in plan.rows)
