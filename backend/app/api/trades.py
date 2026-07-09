"""Manual trade entry — trades CRUD (task 02b), auto-mounted under ``/api``.

Endpoints (``app.api.register_routers`` discovers this module by its ``router``):

- ``POST   /api/trades``                  create a manual trade (``origin='manual'``).
- ``GET    /api/trades?origin=…``         list trades newest-first (default ``manual``),
                                          plus a manual-trade staleness hint.
- ``PATCH  /api/trades/{id}``             edit a **manual** trade (409 on an imported row).
- ``DELETE /api/trades/{id}``             delete a **manual** trade (409 on an imported row).
- ``POST   /api/trades/clear-superseded`` drop manual trades a newer B3 import now covers.

Manual trades layer on top of the imported ``position_summary`` baseline — see
:func:`app.portfolio.positions.build_positions`, which is reused elsewhere and never
modified. Every mutation bumps the evolution "data version" (drops the snapshot cache,
see :mod:`app.portfolio.trades_service`) so the equity curve recomputes; positions are
always computed live so they reflect changes on the next request with no extra step.

Schemas are defined **inline** here (this feature's own module, not shared
``app.schemas``). Business-rule failures raise ``HTTPException``; the shared handler
reshapes them into the ``{"error": …}`` envelope (README §7). Canonical ticker =
uppercase with a trailing fractional ``F`` stripped; money is rounded to 2dp.
"""

from __future__ import annotations

from datetime import date as _date, datetime, timezone
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Transaction
from app.portfolio import trades_service as svc
from app.quotes.base import canonical_ticker, to_money
from app.schemas import APIModel

router = APIRouter(tags=["trades"])

_ORIGINS = ("manual", "import", "all")
# Fields that map to NOT NULL columns — an explicit ``null`` in a PATCH is rejected.
_NON_NULLABLE = ("trade_date", "ticker", "side", "quantity", "price", "market")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------- #
# Schemas (inline — this feature's own module).                               #
# --------------------------------------------------------------------------- #
_Quantity = Annotated[Decimal, Field(gt=0, description="Units traded (> 0).")]
_Price = Annotated[Decimal, Field(gt=0, description="Unit price (> 0).")]


def _canon_ticker(value: str) -> str:
    ticker = canonical_ticker(value)
    if not ticker:
        raise ValueError("ticker é obrigatório.")
    return ticker


class TradeInput(APIModel):
    """Create payload for a manual trade. ``value`` is computed server-side."""

    trade_date: _date
    ticker: str
    side: Literal["buy", "sell"]
    quantity: _Quantity
    price: _Price
    market: str = "a_vista"
    institution: str | None = None
    note: str | None = None

    @field_validator("trade_date")
    @classmethod
    def _not_future(cls, v: _date) -> _date:
        if v > _date.today():
            raise ValueError("trade_date não pode ser no futuro.")
        return v

    @field_validator("ticker")
    @classmethod
    def _canonical(cls, v: str) -> str:
        return _canon_ticker(v)

    @field_validator("market")
    @classmethod
    def _market_default(cls, v: str | None) -> str:
        return (v or "").strip() or "a_vista"

    @field_validator("institution", "note")
    @classmethod
    def _blank_to_none(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return v.strip() or None


class TradeUpdate(APIModel):
    """Partial edit payload — only provided fields are applied (``exclude_unset``)."""

    trade_date: _date | None = None
    ticker: str | None = None
    side: Literal["buy", "sell"] | None = None
    quantity: _Quantity | None = None
    price: _Price | None = None
    market: str | None = None
    institution: str | None = None
    note: str | None = None

    @field_validator("trade_date")
    @classmethod
    def _not_future(cls, v: _date | None) -> _date | None:
        if v is not None and v > _date.today():
            raise ValueError("trade_date não pode ser no futuro.")
        return v

    @field_validator("ticker")
    @classmethod
    def _canonical(cls, v: str | None) -> str | None:
        return _canon_ticker(v) if v is not None else None

    @field_validator("market")
    @classmethod
    def _strip_market(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return v.strip() or "a_vista"

    @field_validator("institution", "note")
    @classmethod
    def _blank_to_none(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return v.strip() or None


class TradeOut(APIModel):
    """One persisted trade row (money/quantity serialized as numbers)."""

    id: int
    trade_date: _date
    ticker: str
    market: str
    side: str
    quantity: float
    price: float
    value: float
    institution: str | None
    origin: str
    note: str | None
    source_file: str | None
    imported_at: datetime


class TradeListResponse(APIModel):
    """``GET /api/trades`` payload: the filtered list + a manual-trade staleness hint.

    ``manual_count`` / ``latest_manual_trade_date`` always describe the manual rows
    (regardless of the ``origin`` filter) so the UI can nudge "you have unsynced
    manual trades — re-import your B3 export to reconcile."
    """

    trades: list[TradeOut]
    count: int
    manual_count: int
    latest_manual_trade_date: _date | None


class ClearSupersededResponse(APIModel):
    """``POST /api/trades/clear-superseded`` result."""

    deleted: int


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #
def _guard_sell(
    db: Session,
    side: str,
    ticker: str,
    quantity: Decimal,
    *,
    exclude_id: int | None,
) -> None:
    """Reject a sell that exceeds the current net quantity held for ``ticker`` (400)."""
    if side != "sell":
        return
    net = svc.current_net_qty(db, ticker, exclude_id=exclude_id)
    if Decimal(quantity) > net:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Venda de {quantity} {canonical_ticker(ticker)} excede a "
                f"quantidade líquida disponível ({net})."
            ),
        )


def _get_manual_or_error(db: Session, trade_id: int) -> Transaction:
    """Load a trade or raise 404 (missing) / 409 (imported, not editable)."""
    trade = db.get(Transaction, trade_id)
    if trade is None:
        raise HTTPException(status_code=404, detail=f"Operação {trade_id} não encontrada.")
    if trade.origin != "manual":
        raise HTTPException(
            status_code=409,
            detail="Operações importadas da B3 não podem ser editadas ou removidas.",
        )
    return trade


# --------------------------------------------------------------------------- #
# Endpoints                                                                    #
# --------------------------------------------------------------------------- #
@router.post("/trades", response_model=TradeOut, status_code=201)
def create_trade(payload: TradeInput, db: Session = Depends(get_db)) -> Transaction:
    """Create a manual trade; returns the created row."""
    _guard_sell(db, payload.side, payload.ticker, payload.quantity, exclude_id=None)
    trade = Transaction(
        trade_date=payload.trade_date,
        ticker=payload.ticker,  # already canonical (validator)
        market=payload.market,
        side=payload.side,
        quantity=payload.quantity,
        price=payload.price,
        value=to_money(payload.quantity * payload.price),
        institution=payload.institution,
        origin="manual",
        note=payload.note,
        source_file=None,
        imported_at=_utcnow(),
    )
    db.add(trade)
    svc.invalidate_snapshots(db)
    db.commit()
    db.refresh(trade)
    return trade


@router.get("/trades", response_model=TradeListResponse)
def list_trades(
    origin: str = Query(default="manual", description="manual | import | all"),
    db: Session = Depends(get_db),
) -> TradeListResponse:
    """List trades newest-first, filtered by ``origin`` (default manual)."""
    if origin not in _ORIGINS:
        raise HTTPException(
            status_code=400,
            detail=f"origin inválido: '{origin}'. Use manual, import ou all.",
        )
    stmt = select(Transaction)
    if origin != "all":
        stmt = stmt.where(Transaction.origin == origin)
    stmt = stmt.order_by(Transaction.trade_date.desc(), Transaction.id.desc())
    rows = list(db.scalars(stmt).all())

    manual_count = db.execute(
        select(func.count())
        .select_from(Transaction)
        .where(Transaction.origin == "manual")
    ).scalar_one()
    latest_manual = db.execute(
        select(func.max(Transaction.trade_date)).where(Transaction.origin == "manual")
    ).scalar_one()

    return TradeListResponse(
        trades=[TradeOut.model_validate(r) for r in rows],
        count=len(rows),
        manual_count=int(manual_count or 0),
        latest_manual_trade_date=latest_manual,
    )


@router.patch("/trades/{trade_id}", response_model=TradeOut)
def update_trade(
    trade_id: int, payload: TradeUpdate, db: Session = Depends(get_db)
) -> Transaction:
    """Edit a manual trade (imported rows are rejected with 409)."""
    trade = _get_manual_or_error(db, trade_id)
    data = payload.model_dump(exclude_unset=True)
    for field in _NON_NULLABLE:
        if field in data and data[field] is None:
            raise HTTPException(status_code=400, detail=f"{field} não pode ser nulo.")

    # Validate the sell guard against the *post-edit* side/ticker/qty, excluding this
    # row from the tally so it does not count against itself.
    new_side = data.get("side", trade.side)
    new_ticker = data.get("ticker", trade.ticker)
    new_qty = data.get("quantity", trade.quantity)
    _guard_sell(db, new_side, new_ticker, new_qty, exclude_id=trade.id)

    for field in (
        "trade_date",
        "ticker",
        "side",
        "quantity",
        "price",
        "market",
        "institution",
        "note",
    ):
        if field in data:
            setattr(trade, field, data[field])
    if "quantity" in data or "price" in data:
        trade.value = to_money(Decimal(trade.quantity) * Decimal(trade.price))
    trade.imported_at = _utcnow()  # bump the data version

    svc.invalidate_snapshots(db)
    db.commit()
    db.refresh(trade)
    return trade


@router.delete("/trades/{trade_id}", status_code=204)
def delete_trade(trade_id: int, db: Session = Depends(get_db)) -> Response:
    """Delete a manual trade (imported rows are rejected with 409)."""
    trade = _get_manual_or_error(db, trade_id)
    db.delete(trade)
    svc.invalidate_snapshots(db)
    db.commit()
    return Response(status_code=204)


@router.post("/trades/clear-superseded", response_model=ClearSupersededResponse)
def clear_superseded(db: Session = Depends(get_db)) -> ClearSupersededResponse:
    """Drop manual trades dated ``<= period_end`` — the fresh baseline now covers them."""
    deleted = svc.delete_superseded_manual(db)
    if deleted:
        svc.invalidate_snapshots(db)
    db.commit()
    return ClearSupersededResponse(deleted=deleted)
