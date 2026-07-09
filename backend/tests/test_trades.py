"""Unit tests for the manual-trade CRUD API (task 02b).

These call the ``app.api.trades`` endpoint functions directly against an isolated
in-memory SQLite session (endpoints take ``db`` as a plain arg, so no FastAPI app /
TestClient is needed — the app auto-imports sibling routers that may be mid-write in a
parallel wave). ``HTTPException`` is asserted directly. Positions/evolution layering is
exercised through the real ``build_positions`` / ``get_evolution_series`` (reused, not
modified) with a mocked quote service.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.api.trades import (
    TradeInput,
    TradeUpdate,
    clear_superseded,
    create_trade,
    delete_trade,
    list_trades,
    update_trade,
)
from app.models import Base, PositionSummary, Snapshot, Transaction
from app.portfolio.positions import build_positions
from app.portfolio.evolution import get_evolution_series
from app.quotes.base import DailyClose, Quote


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


# --------------------------------------------------------------------------- #
# Test helpers                                                                #
# --------------------------------------------------------------------------- #
class FakeQuoteService:
    """Latest-price + history stand-in for QuoteService."""

    def __init__(self, price: str = "10"):
        self._price = Decimal(price)

    def latest(self, tickers):
        return {t: Quote(price=self._price, date=date(2025, 1, 3), source="test") for t in tickers}

    def history(self, ticker, start, end):
        return [DailyClose(date=start, close=self._price)]


def _summary(ticker: str, qty: str, avg: str, period_end=date(2024, 12, 31)) -> PositionSummary:
    return PositionSummary(
        ticker=ticker, qty_net=Decimal(qty), avg_price_buy=Decimal(avg), period_end=period_end
    )


def _payload(**over):
    base = dict(
        trade_date=date(2025, 1, 15),
        ticker="ITSA4",
        side="buy",
        quantity=Decimal("100"),
        price=Decimal("20"),
    )
    base.update(over)
    return TradeInput(**base)


# --------------------------------------------------------------------------- #
# Create                                                                      #
# --------------------------------------------------------------------------- #
def test_create_sets_origin_manual_and_computes_value(db):
    out = create_trade(_payload(), db=db)
    assert out.origin == "manual"
    assert out.value == 2000.0  # 100 * 20
    assert out.source_file is None
    assert out.id is not None
    row = db.get(Transaction, out.id)
    assert row.origin == "manual"
    assert row.value == Decimal("2000.00")


def test_create_canonicalizes_ticker(db):
    out = create_trade(_payload(ticker="itsa4f"), db=db)  # lowercase + trailing F
    assert out.ticker == "ITSA4"


def test_create_rejects_future_date():
    with pytest.raises(ValidationError):
        _payload(trade_date=date.today() + timedelta(days=1))


@pytest.mark.parametrize("bad", [Decimal("0"), Decimal("-5")])
def test_create_rejects_nonpositive_quantity(bad):
    with pytest.raises(ValidationError):
        _payload(quantity=bad)


def test_create_rejects_nonpositive_price():
    with pytest.raises(ValidationError):
        _payload(price=Decimal("0"))


# --------------------------------------------------------------------------- #
# Sell guard                                                                  #
# --------------------------------------------------------------------------- #
def test_sell_exceeding_net_qty_is_rejected_400(db):
    db.add(_summary("ITSA4", "100", "10", period_end=date(2024, 12, 31)))
    db.commit()
    with pytest.raises(HTTPException) as exc:
        create_trade(
            _payload(ticker="ITSA4", side="sell", quantity=Decimal("150"),
                     trade_date=date(2025, 2, 1)),
            db=db,
        )
    assert exc.value.status_code == 400
    assert "excede" in exc.value.detail


def test_sell_within_net_qty_is_accepted(db):
    db.add(_summary("ITSA4", "100", "10", period_end=date(2024, 12, 31)))
    db.commit()
    out = create_trade(
        _payload(ticker="ITSA4", side="sell", quantity=Decimal("40"),
                 price=Decimal("15"), trade_date=date(2025, 2, 1)),
        db=db,
    )
    assert out.side == "sell"
    assert out.quantity == 40.0


def test_sell_net_qty_includes_prior_manual_buys(db):
    # No baseline at all -> every manual trade counts. Buy 30 then sell 30 is OK,
    # a further sell overdraws.
    create_trade(_payload(ticker="ABCD3", side="buy", quantity=Decimal("30"),
                          trade_date=date(2025, 1, 2)), db=db)
    out = create_trade(_payload(ticker="ABCD3", side="sell", quantity=Decimal("30"),
                                trade_date=date(2025, 1, 3)), db=db)
    assert out.side == "sell"
    with pytest.raises(HTTPException) as exc:
        create_trade(_payload(ticker="ABCD3", side="sell", quantity=Decimal("1"),
                              trade_date=date(2025, 1, 4)), db=db)
    assert exc.value.status_code == 400


# --------------------------------------------------------------------------- #
# List                                                                        #
# --------------------------------------------------------------------------- #
def test_list_default_manual_newest_first_with_hint(db):
    create_trade(_payload(ticker="AAAA3", trade_date=date(2025, 1, 10)), db=db)
    create_trade(_payload(ticker="BBBB3", trade_date=date(2025, 3, 5)), db=db)
    # an imported row that must NOT show up under the default manual filter
    db.add(
        Transaction(
            trade_date=date(2025, 2, 1), ticker="CCCC3", market="a_vista", side="buy",
            quantity=Decimal("1"), price=Decimal("1"), value=Decimal("1"), origin="import",
        )
    )
    db.commit()

    resp = list_trades(origin="manual", db=db)
    assert [t.ticker for t in resp.trades] == ["BBBB3", "AAAA3"]  # newest first
    assert resp.count == 2
    assert resp.manual_count == 2
    assert resp.latest_manual_trade_date == date(2025, 3, 5)


def test_list_origin_import_and_all(db):
    create_trade(_payload(ticker="AAAA3", trade_date=date(2025, 1, 10)), db=db)
    db.add(
        Transaction(
            trade_date=date(2025, 2, 1), ticker="CCCC3", market="a_vista", side="buy",
            quantity=Decimal("1"), price=Decimal("1"), value=Decimal("1"), origin="import",
        )
    )
    db.commit()

    imported = list_trades(origin="import", db=db)
    assert [t.ticker for t in imported.trades] == ["CCCC3"]
    assert imported.manual_count == 1  # hint always reflects manual rows

    every = list_trades(origin="all", db=db)
    assert {t.ticker for t in every.trades} == {"AAAA3", "CCCC3"}
    assert every.count == 2


def test_list_invalid_origin_400(db):
    with pytest.raises(HTTPException) as exc:
        list_trades(origin="bogus", db=db)
    assert exc.value.status_code == 400


# --------------------------------------------------------------------------- #
# Update                                                                      #
# --------------------------------------------------------------------------- #
def test_update_manual_recomputes_value_and_bumps_version(db):
    out = create_trade(_payload(ticker="ITSA4", quantity=Decimal("10"), price=Decimal("10")), db=db)
    before = db.get(Transaction, out.id).imported_at
    updated = update_trade(
        out.id, TradeUpdate(quantity=Decimal("20"), price=Decimal("30")), db=db
    )
    assert updated.quantity == 20.0
    assert updated.price == 30.0
    assert updated.value == 600.0  # recomputed 20 * 30
    assert db.get(Transaction, out.id).imported_at >= before


def test_update_partial_leaves_other_fields(db):
    out = create_trade(_payload(ticker="ITSA4", note=None), db=db)
    updated = update_trade(out.id, TradeUpdate(note="ajuste"), db=db)
    assert updated.note == "ajuste"
    assert updated.ticker == "ITSA4"
    assert updated.value == 2000.0  # untouched


def test_update_import_row_is_409(db):
    db.add(
        Transaction(
            trade_date=date(2025, 2, 1), ticker="CCCC3", market="a_vista", side="buy",
            quantity=Decimal("1"), price=Decimal("1"), value=Decimal("1"), origin="import",
        )
    )
    db.commit()
    imported_id = db.scalars(select(Transaction.id)).first()
    with pytest.raises(HTTPException) as exc:
        update_trade(imported_id, TradeUpdate(quantity=Decimal("5")), db=db)
    assert exc.value.status_code == 409


def test_update_missing_row_is_404(db):
    with pytest.raises(HTTPException) as exc:
        update_trade(999, TradeUpdate(note="x"), db=db)
    assert exc.value.status_code == 404


def test_update_to_oversell_is_rejected(db):
    db.add(_summary("ITSA4", "100", "10", period_end=date(2024, 12, 31)))
    db.commit()
    sell = create_trade(
        _payload(ticker="ITSA4", side="sell", quantity=Decimal("40"),
                 price=Decimal("15"), trade_date=date(2025, 2, 1)),
        db=db,
    )
    # Editing the same sell up to 200 (> 100 net) must be rejected, and the row must
    # not count against itself (exclude_id).
    with pytest.raises(HTTPException) as exc:
        update_trade(sell.id, TradeUpdate(quantity=Decimal("200")), db=db)
    assert exc.value.status_code == 400
    # But bumping it to exactly the net (100) is fine.
    ok = update_trade(sell.id, TradeUpdate(quantity=Decimal("100")), db=db)
    assert ok.quantity == 100.0


# --------------------------------------------------------------------------- #
# Delete                                                                      #
# --------------------------------------------------------------------------- #
def test_delete_manual_removes_row(db):
    out = create_trade(_payload(), db=db)
    resp = delete_trade(out.id, db=db)
    assert resp.status_code == 204
    assert db.get(Transaction, out.id) is None


def test_delete_import_row_is_409(db):
    db.add(
        Transaction(
            trade_date=date(2025, 2, 1), ticker="CCCC3", market="a_vista", side="buy",
            quantity=Decimal("1"), price=Decimal("1"), value=Decimal("1"), origin="import",
        )
    )
    db.commit()
    imported_id = db.scalars(select(Transaction.id)).first()
    with pytest.raises(HTTPException) as exc:
        delete_trade(imported_id, db=db)
    assert exc.value.status_code == 409
    assert db.get(Transaction, imported_id) is not None  # untouched


def test_delete_missing_row_is_404(db):
    with pytest.raises(HTTPException) as exc:
        delete_trade(999, db=db)
    assert exc.value.status_code == 404


# --------------------------------------------------------------------------- #
# Data-version bump (snapshot cache invalidation)                             #
# --------------------------------------------------------------------------- #
def _seed_snapshot(db):
    db.add(Snapshot(date=date(2025, 1, 1), total_value=Decimal("1"), total_cost=Decimal("1")))
    db.commit()


def test_create_invalidates_snapshot_cache(db):
    _seed_snapshot(db)
    create_trade(_payload(), db=db)
    assert db.scalars(select(Snapshot)).all() == []


def test_delete_invalidates_snapshot_cache(db):
    out = create_trade(_payload(), db=db)
    _seed_snapshot(db)
    delete_trade(out.id, db=db)
    assert db.scalars(select(Snapshot)).all() == []


# --------------------------------------------------------------------------- #
# Positions & evolution integration (reused builders, not modified)          #
# --------------------------------------------------------------------------- #
def test_manual_buy_updates_positions_weighted_avg(db):
    db.add(_summary("ITSA4", "100", "10", period_end=date(2024, 12, 31)))
    db.commit()
    create_trade(
        _payload(ticker="ITSA4", side="buy", quantity=Decimal("100"),
                 price=Decimal("20"), trade_date=date(2025, 1, 15)),
        db=db,
    )
    view = build_positions(db, quote_service=FakeQuoteService("15"))
    p = next(p for p in view.positions if p.ticker == "ITSA4")
    assert p.quantity == 200.0
    assert p.avg_price == 15.0  # (100*10 + 100*20) / 200


def test_manual_sell_reduces_positions_quantity(db):
    db.add(_summary("ITSA4", "100", "10", period_end=date(2024, 12, 31)))
    db.commit()
    create_trade(
        _payload(ticker="ITSA4", side="sell", quantity=Decimal("40"),
                 price=Decimal("15"), trade_date=date(2025, 2, 1)),
        db=db,
    )
    view = build_positions(db, quote_service=FakeQuoteService("15"))
    p = next(p for p in view.positions if p.ticker == "ITSA4")
    assert p.quantity == 60.0


def test_manual_trade_appears_in_evolution_series(db):
    # No baseline: a manual buy alone must show up in the reconstructed equity curve.
    create_trade(
        _payload(ticker="ABCD3", side="buy", quantity=Decimal("10"),
                 price=Decimal("5"), trade_date=date(2025, 1, 2)),
        db=db,
    )
    series = get_evolution_series(
        db, quote_service=FakeQuoteService("8"), to=date(2025, 1, 3)
    )
    assert series.points, "expected a non-empty evolution series"
    assert series.points[-1].market_value == Decimal("80.00")  # 10 * 8


# --------------------------------------------------------------------------- #
# Superseded manual trades                                                    #
# --------------------------------------------------------------------------- #
def test_clear_superseded_removes_only_pre_cutoff_manual(db):
    # Baseline period_end = 2025-01-31. A manual trade dated on/before it is now
    # covered by the fresh baseline; one dated after is still live.
    db.add(_summary("ITSA4", "100", "10", period_end=date(2025, 1, 31)))
    db.commit()
    # Insert a superseded manual row directly (a pre-cutoff date the create-guard for a
    # sell would still allow as a buy).
    db.add(
        Transaction(
            trade_date=date(2025, 1, 10), ticker="ITSA4", market="a_vista", side="buy",
            quantity=Decimal("50"), price=Decimal("12"), value=Decimal("600"), origin="manual",
        )
    )
    db.commit()
    live = create_trade(
        _payload(ticker="ITSA4", side="buy", quantity=Decimal("20"),
                 price=Decimal("25"), trade_date=date(2025, 2, 15)),
        db=db,
    )

    resp = clear_superseded(db=db)
    assert resp.deleted == 1
    remaining = db.scalars(select(Transaction).where(Transaction.origin == "manual")).all()
    assert [t.id for t in remaining] == [live.id]


def test_clear_superseded_noop_without_baseline(db):
    create_trade(_payload(ticker="ABCD3", trade_date=date(2025, 1, 2)), db=db)
    resp = clear_superseded(db=db)
    assert resp.deleted == 0


# --------------------------------------------------------------------------- #
# Re-import preserves manual rows (origin-scoped delete — cross-cutting)      #
# --------------------------------------------------------------------------- #
def test_reimport_preserves_manual_rows(db):
    from app.ingestion import service as ingestion_service

    create_trade(_payload(ticker="ITSA4"), db=db)
    db.add(
        Transaction(
            trade_date=date(2025, 1, 1), ticker="OLD3", market="a_vista", side="buy",
            quantity=Decimal("1"), price=Decimal("1"), value=Decimal("1"), origin="import",
        )
    )
    db.commit()

    # A re-import replaces only origin='import' rows.
    ingestion_service._replace_transactions(db, [], filename="negociacao.xlsx")
    db.commit()

    remaining = db.scalars(select(Transaction)).all()
    assert [t.origin for t in remaining] == ["manual"]
    assert remaining[0].ticker == "ITSA4"
