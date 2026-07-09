"""SQLAlchemy 2.0 ORM models — the persistence contract for tasks 02-13.

Field names here are load-bearing: later layers (ingestion, quotes, positions,
evolution, rebalancing, accounting) read/write these exact columns. Conventions:
canonical ticker = uppercase, no trailing `F`; dates stored ISO (`DATE`); money in
`Numeric` (2dp at the domain layer per README §7).

CNPJ overrides intentionally do NOT live here — they stay in the legacy xlsx via
`core.save_overrides` for accounting compatibility (see task 01, step 4 note).
"""

from datetime import date as _date, datetime as _datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    Date,
    DateTime,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _utcnow() -> _datetime:
    return _datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


class Transaction(Base):
    """One row per trade — from the *histórico* export or manual entry (task 02b).

    `origin` distinguishes imported vs. manual rows so a re-import can replace only
    `origin='import'` rows while preserving manual ones.
    """

    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    trade_date: Mapped[_date] = mapped_column(Date, nullable=False, index=True)
    ticker: Mapped[str] = mapped_column(String, nullable=False, index=True)
    market: Mapped[str] = mapped_column(String, nullable=False)  # 'a_vista' | 'fracionario'
    side: Mapped[str] = mapped_column(String, nullable=False)  # 'buy' | 'sell'
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    value: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    institution: Mapped[str | None] = mapped_column(String, nullable=True)
    origin: Mapped[str] = mapped_column(
        String, nullable=False, default="import", server_default="import"
    )  # 'import' | 'manual'
    note: Mapped[str | None] = mapped_column(String, nullable=True)
    source_file: Mapped[str | None] = mapped_column(String, nullable=True)
    imported_at: Mapped[_datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow, server_default=func.now()
    )


class PositionSummary(Base):
    """One row per ticker — from the *Negociação - Resumo* export."""

    __tablename__ = "position_summary"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String, nullable=False, index=True)
    institution: Mapped[str | None] = mapped_column(String, nullable=True)
    qty_buy: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=True)
    qty_sell: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=True)
    qty_net: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=True)
    avg_price_buy: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=True)
    avg_price_sell: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=True)
    period_start: Mapped[_date | None] = mapped_column(Date, nullable=True)
    period_end: Mapped[_date | None] = mapped_column(Date, nullable=True)
    imported_at: Mapped[_datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow, server_default=func.now()
    )


class Provento(Base):
    """Income event — from the *Proventos Recebidos* export."""

    __tablename__ = "proventos"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String, nullable=False, index=True)
    pay_date: Mapped[_date | None] = mapped_column(Date, nullable=True)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    institution: Mapped[str | None] = mapped_column(String, nullable=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=True)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=True)
    net_value: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=True)
    source_file: Mapped[str | None] = mapped_column(String, nullable=True)
    imported_at: Mapped[_datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow, server_default=func.now()
    )


class TargetAllocation(Base):
    """Desired portfolio weights (task 06). Unique per (kind, key)."""

    __tablename__ = "target_allocations"
    __table_args__ = (UniqueConstraint("kind", "key", name="uq_target_kind_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String, nullable=False)  # 'ticker' | 'class'
    key: Mapped[str] = mapped_column(String, nullable=False)
    target_pct: Mapped[Decimal] = mapped_column(Numeric(9, 4), nullable=False)


class QuoteCache(Base):
    """Daily closes cached from the quote providers (task 03). PK = (ticker, date)."""

    __tablename__ = "quote_cache"

    ticker: Mapped[str] = mapped_column(String, primary_key=True)
    date: Mapped[_date] = mapped_column(Date, primary_key=True)
    close: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    source: Mapped[str | None] = mapped_column(String, nullable=True)  # 'brapi' | 'yfinance'
    fetched_at: Mapped[_datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow, server_default=func.now()
    )


class Snapshot(Base):
    """Cached equity-curve point per day (tasks 05/13). PK = date."""

    __tablename__ = "snapshots"

    date: Mapped[_date] = mapped_column(Date, primary_key=True)
    total_value: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=True)
    total_cost: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=True)
    contributions_to_date: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=True)
    cumulative_proventos: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=True)
    computed_at: Mapped[_datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow, server_default=func.now()
    )
