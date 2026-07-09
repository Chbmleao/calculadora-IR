"""Unit tests for the positions & allocation builder (task 04).

These exercise ``build_positions`` and the classifier directly against an isolated
in-memory SQLite session with a mocked quote service — no FastAPI app / TestClient
(the app auto-imports sibling routers that may be mid-write during a parallel wave).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.models import Base, PositionSummary, Provento, QuoteCache, Transaction
from app.portfolio.classify import classify, display_class
from app.portfolio.positions import build_positions
from app.quotes.base import Quote


@pytest.fixture
def db() -> Session:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, future=True
    )
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
        ticker=ticker,
        qty_net=Decimal(qty),
        avg_price_buy=Decimal(avg),
        period_end=period_end,
    )


def _quote(price: str, on=date(2025, 1, 2)) -> Quote:
    return Quote(price=Decimal(price), date=on, source="test")


# --------------------------------------------------------------------------- #
# Classification                                                              #
# --------------------------------------------------------------------------- #
def test_display_class_rules():
    assert display_class("IVVB11") == "ETF"
    assert display_class("SMAL11") == "ETF"
    assert display_class("HGLG11") == "FII"
    assert display_class("AAPL34") == "BDR"
    assert display_class("ITSA4") == "Ação"
    # canonicalization: trailing F stripped, lowercase accepted
    assert display_class("itsa4f") == "Ação"


def test_classify_returns_dirpf_group_and_code():
    fii = classify("HGLG11")
    assert fii.asset_class == "FII"
    assert fii.dirpf_group.startswith("07")
    assert fii.dirpf_code.startswith("03")

    etf = classify("IVVB11")
    assert etf.asset_class == "ETF"
    assert "ETF" in etf.dirpf_code

    acao = classify("ITSA4")
    assert acao.asset_class == "Ação"
    assert acao.dirpf_group.startswith("03")


# --------------------------------------------------------------------------- #
# Weights + class grouping                                                    #
# --------------------------------------------------------------------------- #
def test_weights_sum_to_100_and_class_grouping(db):
    db.add_all(
        [
            _summary("ITSA4", "100", "10"),  # Ação, mv = 1200
            _summary("HGLG11", "10", "100"),  # FII, mv = 1100
            _summary("IVVB11", "5", "200"),  # ETF, mv = 1000
        ]
    )
    db.commit()

    quotes = FakeQuoteService(
        {"ITSA4": _quote("12"), "HGLG11": _quote("110"), "IVVB11": _quote("200")}
    )
    view = build_positions(db, quote_service=quotes)

    assert view.message is None
    assert view.totals.market_value == 3300.0  # 1200 + 1100 + 1000
    assert view.totals.invested == 3000.0  # 1000 + 1000 + 1000

    # Per-ticker weights sum to ~100.
    assert abs(sum(p.weight_pct for p in view.positions) - 100) < 0.1
    # Class weights sum to ~100.
    assert abs(sum(a.weight_pct for a in view.allocation_by_class) - 100) < 0.1

    # Class grouping is correct and matches per-ticker market-value sums.
    by_class = {a.asset_class: a.market_value for a in view.allocation_by_class}
    assert set(by_class) == {"Ação", "FII", "ETF"}
    assert by_class["Ação"] == 1200.0
    assert by_class["FII"] == 1100.0
    assert by_class["ETF"] == 1000.0

    per_ticker_class_sum: dict[str, float] = {}
    for p in view.positions:
        per_ticker_class_sum[p.asset_class] = per_ticker_class_sum.get(p.asset_class, 0.0) + p.market_value
    assert per_ticker_class_sum == by_class


def test_pnl_computation(db):
    db.add(_summary("ITSA4", "100", "10"))  # invested 1000, mv 1200
    db.commit()
    view = build_positions(db, quote_service=FakeQuoteService({"ITSA4": _quote("12")}))
    p = view.positions[0]
    assert p.invested == 1000.0
    assert p.market_value == 1200.0
    assert p.pnl == 200.0
    assert p.pnl_pct == 20.0
    assert p.stale is False
    assert p.price == 12.0
    assert p.price_date == date(2025, 1, 2)
    assert view.as_of == date(2025, 1, 2)


# --------------------------------------------------------------------------- #
# Stale / missing-price handling                                             #
# --------------------------------------------------------------------------- #
def test_missing_quote_marks_stale_without_crash(db):
    db.add(_summary("XPML11", "5", "100"))  # invested 500
    db.commit()
    view = build_positions(db, quote_service=FakeQuoteService({}))  # no prices at all
    p = view.positions[0]
    assert p.stale is True
    assert p.price is None
    assert p.price_date is None
    assert p.market_value == p.invested == 500.0  # invested-value fallback
    assert p.pnl == 0.0
    assert p.pnl_pct == 0.0


def test_stale_falls_back_to_last_cached_close(db):
    db.add(_summary("ITSA4", "100", "10"))
    db.add(QuoteCache(ticker="ITSA4", date=date(2025, 1, 2), close=Decimal("11"), source="cache"))
    db.commit()
    view = build_positions(db, quote_service=FakeQuoteService({}))  # live quote missing
    p = view.positions[0]
    assert p.stale is True
    assert p.price == 11.0
    assert p.market_value == 1100.0
    assert p.price_date == date(2025, 1, 2)


# --------------------------------------------------------------------------- #
# Proventos                                                                   #
# --------------------------------------------------------------------------- #
def test_proventos_per_ticker_and_total(db):
    db.add_all([_summary("ITSA4", "100", "10"), _summary("HGLG11", "10", "100")])
    db.add_all(
        [
            Provento(ticker="ITSA4", event_type="Dividendo", net_value=Decimal("50")),
            Provento(ticker="ITSA4", event_type="JCP", net_value=Decimal("25")),
            Provento(ticker="HGLG11", event_type="Rendimento", net_value=Decimal("30")),
        ]
    )
    db.commit()
    view = build_positions(
        db,
        quote_service=FakeQuoteService({"ITSA4": _quote("12"), "HGLG11": _quote("110")}),
    )
    prov = {p.ticker: p.proventos_total for p in view.positions}
    assert prov["ITSA4"] == 75.0
    assert prov["HGLG11"] == 30.0
    assert view.totals.proventos == 105.0


# --------------------------------------------------------------------------- #
# Empty view                                                                  #
# --------------------------------------------------------------------------- #
def test_empty_view_has_message_not_crash(db):
    view = build_positions(db, quote_service=FakeQuoteService({}))
    assert view.positions == []
    assert view.allocation_by_class == []
    assert view.message is not None
    assert view.totals.market_value == 0.0
    assert view.as_of is None


# --------------------------------------------------------------------------- #
# Manual delta (task 02b) layering                                           #
# --------------------------------------------------------------------------- #
def test_manual_buy_after_period_recomputes_avg(db):
    db.add(_summary("ITSA4", "100", "10", period_end=date(2024, 12, 31)))
    db.add(
        Transaction(
            trade_date=date(2025, 1, 15),
            ticker="ITSA4",
            market="a_vista",
            side="buy",
            quantity=Decimal("100"),
            price=Decimal("20"),
            value=Decimal("2000"),
            origin="manual",
        )
    )
    db.commit()
    view = build_positions(db, quote_service=FakeQuoteService({"ITSA4": _quote("15")}))
    p = view.positions[0]
    assert p.quantity == 200.0
    assert p.avg_price == 15.0  # (100*10 + 100*20) / 200
    assert p.invested == 3000.0
    assert p.market_value == 3000.0


def test_manual_sell_reducing_to_zero_drops_ticker(db):
    db.add(_summary("ITSA4", "100", "10", period_end=date(2024, 12, 31)))
    db.add(
        Transaction(
            trade_date=date(2025, 2, 1),
            ticker="ITSA4",
            market="a_vista",
            side="sell",
            quantity=Decimal("100"),
            price=Decimal("15"),
            value=Decimal("1500"),
            origin="manual",
        )
    )
    db.commit()
    view = build_positions(db, quote_service=FakeQuoteService({"ITSA4": _quote("15")}))
    assert view.positions == []
    assert view.message is not None


def test_manual_trade_before_period_is_ignored(db):
    # Trade dated before/at the summary period_end is already reflected in the baseline.
    db.add(_summary("ITSA4", "100", "10", period_end=date(2024, 12, 31)))
    db.add(
        Transaction(
            trade_date=date(2024, 6, 1),
            ticker="ITSA4",
            market="a_vista",
            side="buy",
            quantity=Decimal("100"),
            price=Decimal("20"),
            value=Decimal("2000"),
            origin="manual",
        )
    )
    db.commit()
    view = build_positions(db, quote_service=FakeQuoteService({"ITSA4": _quote("12")}))
    p = view.positions[0]
    assert p.quantity == 100.0
    assert p.avg_price == 10.0


def test_import_origin_trades_never_layer(db):
    # Only origin='manual' trades layer on top of the baseline.
    db.add(_summary("ITSA4", "100", "10", period_end=date(2024, 12, 31)))
    db.add(
        Transaction(
            trade_date=date(2025, 3, 1),
            ticker="ITSA4",
            market="a_vista",
            side="buy",
            quantity=Decimal("50"),
            price=Decimal("20"),
            value=Decimal("1000"),
            origin="import",
        )
    )
    db.commit()
    view = build_positions(db, quote_service=FakeQuoteService({"ITSA4": _quote("12")}))
    assert view.positions[0].quantity == 100.0
