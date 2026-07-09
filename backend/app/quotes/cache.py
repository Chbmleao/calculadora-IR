"""SQLite cache for daily closes (task 03), backed by the ``quote_cache`` table.

Caching cuts request volume against brapi/yfinance and lets the app survive a
provider outage. Rows are keyed ``(ticker, date)``; ``fetched_at`` records when the
row was written so a *latest* quote can be judged fresh within a TTL.

All reads/writes canonicalize the ticker and quantize the close to 2dp so the
cache never disagrees with the domain layer on ticker spelling or money precision.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date as _date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import QuoteCache
from app.quotes.base import DailyClose, canonical_ticker, to_money


@dataclass(frozen=True)
class CacheRow:
    """A row to upsert into ``quote_cache``."""

    ticker: str
    date: _date
    close: Decimal
    source: str | None = None


def _now_utc_naive() -> datetime:
    """Current UTC as a naive datetime (SQLite stores/returns naive UTC)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _as_naive_utc(dt: datetime) -> datetime:
    """Normalize a possibly-aware datetime to naive UTC for comparison."""
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def is_fresh(fetched_at: datetime | None, ttl_minutes: int) -> bool:
    """True when ``fetched_at`` is within ``ttl_minutes`` of now (UTC)."""
    if fetched_at is None:
        return False
    if ttl_minutes <= 0:
        return False
    age = _now_utc_naive() - _as_naive_utc(fetched_at)
    return timedelta(0) <= age <= timedelta(minutes=ttl_minutes)


def get_cached_history(db: Session, ticker: str, start: _date, end: _date) -> list[DailyClose]:
    """Return cached daily closes for ``ticker`` within ``[start, end]`` (ascending)."""
    canon = canonical_ticker(ticker)
    stmt = (
        select(QuoteCache)
        .where(
            QuoteCache.ticker == canon,
            QuoteCache.date >= start,
            QuoteCache.date <= end,
        )
        .order_by(QuoteCache.date)
    )
    rows = db.scalars(stmt).all()
    return [DailyClose(date=r.date, close=r.close) for r in rows]


def get_cached_dates(db: Session, ticker: str, start: _date, end: _date) -> set[_date]:
    """Return the set of dates already cached for ``ticker`` within the range."""
    canon = canonical_ticker(ticker)
    stmt = select(QuoteCache.date).where(
        QuoteCache.ticker == canon,
        QuoteCache.date >= start,
        QuoteCache.date <= end,
    )
    return set(db.scalars(stmt).all())


def get_latest_cached(db: Session, ticker: str) -> QuoteCache | None:
    """Return the most recent cached row (by date) for ``ticker``, or ``None``."""
    canon = canonical_ticker(ticker)
    stmt = (
        select(QuoteCache)
        .where(QuoteCache.ticker == canon)
        .order_by(QuoteCache.date.desc())
        .limit(1)
    )
    return db.scalars(stmt).first()


def upsert(db: Session, rows: Iterable[CacheRow]) -> int:
    """Insert or update cache rows; returns the number of rows written.

    Refreshes ``fetched_at`` on every touched row so latest-quote freshness tracks
    the last time we actually fetched the price.
    """
    now = _now_utc_naive()
    count = 0
    for row in rows:
        canon = canonical_ticker(row.ticker)
        close = to_money(row.close)
        existing = db.get(QuoteCache, (canon, row.date))
        if existing is not None:
            existing.close = close
            existing.source = row.source
            existing.fetched_at = now
        else:
            db.add(
                QuoteCache(
                    ticker=canon,
                    date=row.date,
                    close=close,
                    source=row.source,
                    fetched_at=now,
                )
            )
        count += 1
    if count:
        db.commit()
    return count
