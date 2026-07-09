"""QuoteService — cache-first quotes with brapi→yfinance fallback (task 03).

Responsibilities:
- ``latest(tickers)``   : serve fresh cached quotes; fetch the rest (brapi, then
  yfinance), cache them, and never crash on a single missing ticker.
- ``history(t, s, e)``  : serve from cache and **delta-fetch** only the missing
  head/tail date ranges; ranges older than brapi's ~1y free window go to yfinance.
- ``refresh_latest``    : force a network refresh (used by the scheduler, task 13).

The service programs against the :class:`QuoteProvider` protocol, so brapi/yfinance
are swappable and trivially mockable in tests. Weekend/holiday forward-fill is the
consumer's job (task 05), not the cache's.
"""

from __future__ import annotations

import logging
from datetime import date as _date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.models import PositionSummary, Transaction
from app.quotes import cache
from app.quotes.base import DailyClose, ProviderError, Quote, canonical_ticker
from app.quotes.brapi import BrapiProvider
from app.quotes.cache import CacheRow
from app.quotes.yfinance_provider import YFinanceProvider

logger = logging.getLogger(__name__)

# brapi's free tier serves ~1 year of history; anything older comes from yfinance.
_BRAPI_HISTORY_DAYS = 365
_ONE_DAY = timedelta(days=1)


class QuoteService:
    """Cache-first quote resolution over a set of pluggable providers."""

    def __init__(
        self,
        db: Session,
        *,
        brapi: object | None = None,
        yfinance: object | None = None,
        settings: Settings | None = None,
    ):
        self.db = db
        self.settings = settings or get_settings()
        self.ttl_minutes = self.settings.QUOTE_CACHE_TTL_MINUTES

        # Injected providers win (tests). Otherwise build the real ones; brapi is
        # only used when a token is configured (empty token => yfinance-only, per
        # config.py). ``_explicit_brapi`` records that a caller forced brapi on.
        self._explicit_brapi = brapi is not None
        if brapi is not None:
            self.brapi = brapi
        elif self.settings.BRAPI_TOKEN.strip():
            self.brapi = BrapiProvider(self.settings.BRAPI_BASE_URL, self.settings.BRAPI_TOKEN)
        else:
            self.brapi = None
        self.yfinance = yfinance if yfinance is not None else YFinanceProvider()

    # -- Latest ------------------------------------------------------------

    def latest(self, tickers: list[str]) -> dict[str, Quote]:
        """Latest price per ticker, cache-first (fresh within TTL)."""
        return self._resolve_latest(tickers, force=False)

    def refresh_latest(self, tickers: list[str]) -> dict[str, Quote]:
        """Force-refresh latest prices from providers, ignoring cache freshness."""
        return self._resolve_latest(tickers, force=True)

    def _resolve_latest(self, tickers: list[str], *, force: bool) -> dict[str, Quote]:
        canon = _unique_canonical(tickers)
        resolved: dict[str, Quote] = {}
        to_fetch: list[str] = []

        for ticker in canon:
            if not force:
                cached = cache.get_latest_cached(self.db, ticker)
                if cached is not None and cache.is_fresh(cached.fetched_at, self.ttl_minutes):
                    resolved[ticker] = Quote(
                        price=cached.close,
                        date=cached.date,
                        source=cached.source or "cache",
                    )
                    continue
            to_fetch.append(ticker)

        if to_fetch:
            fetched = self._fetch_latest(to_fetch)
            if fetched:
                cache.upsert(
                    self.db,
                    [
                        CacheRow(ticker=t, date=q.date, close=q.price, source=q.source)
                        for t, q in fetched.items()
                    ],
                )
            resolved.update(fetched)

        missing = [t for t in canon if t not in resolved]
        if missing:
            logger.warning("no quote resolved for %s", missing)
        return resolved

    def _fetch_latest(self, tickers: list[str]) -> dict[str, Quote]:
        """brapi (batch) first; whatever it can't resolve falls back to yfinance."""
        result: dict[str, Quote] = {}
        if self.brapi is not None:
            try:
                result.update(self.brapi.latest(tickers))
            except ProviderError as exc:
                logger.warning("brapi latest failed, falling back to yfinance: %s", exc)

        remaining = [t for t in tickers if t not in result]
        if remaining:
            try:
                result.update(self.yfinance.latest(remaining))
            except ProviderError as exc:
                logger.warning("yfinance latest failed for %s: %s", remaining, exc)
        return result

    # -- History -----------------------------------------------------------

    def history(self, ticker: str, start: _date, end: _date) -> list[DailyClose]:
        """Daily closes for ``ticker`` over ``[start, end]``, delta-fetching gaps."""
        canon = canonical_ticker(ticker)
        if start > end:
            return []

        cached = cache.get_cached_history(self.db, canon, start, end)
        cached_dates = {dc.date for dc in cached}

        merged: dict[_date, DailyClose] = {dc.date: dc for dc in cached}
        new_rows: list[CacheRow] = []

        for range_start, range_end in _missing_ranges(cached_dates, start, end):
            fetched = self._fetch_history(canon, range_start, range_end)
            for day, (close, source) in fetched.items():
                if start <= day <= end:
                    merged[day] = DailyClose(date=day, close=close)
                    if day not in cached_dates:
                        new_rows.append(
                            CacheRow(ticker=canon, date=day, close=close, source=source)
                        )

        if new_rows:
            cache.upsert(self.db, new_rows)

        return [merged[day] for day in sorted(merged)]

    def _fetch_history(
        self, ticker: str, start: _date, end: _date
    ) -> dict[_date, tuple]:
        """Fetch a contiguous span, routing old ranges to yfinance, recent to brapi.

        Returns ``{date: (close, source)}``.
        """
        out: dict[_date, tuple] = {}
        brapi_floor = _date.today() - timedelta(days=_BRAPI_HISTORY_DAYS)

        # Portion older than brapi's free window -> yfinance (long history).
        if start < brapi_floor:
            old_end = min(end, brapi_floor - _ONE_DAY)
            if start <= old_end:
                for dc in self._yf_history(ticker, start, old_end):
                    out[dc.date] = (dc.close, self.yfinance.name)

        # Recent portion -> brapi, falling back to yfinance.
        recent_start = max(start, brapi_floor)
        if recent_start <= end:
            rows, source = self._recent_history(ticker, recent_start, end)
            for dc in rows:
                out[dc.date] = (dc.close, source)
        return out

    def _recent_history(self, ticker: str, start: _date, end: _date) -> tuple[list, str]:
        if self.brapi is not None:
            try:
                return self.brapi.history(ticker, start, end), self.brapi.name
            except ProviderError as exc:
                logger.warning(
                    "brapi history failed for %s, falling back to yfinance: %s", ticker, exc
                )
        return self._yf_history(ticker, start, end), self.yfinance.name

    def _yf_history(self, ticker: str, start: _date, end: _date) -> list:
        try:
            return self.yfinance.history(ticker, start, end)
        except ProviderError as exc:
            logger.warning("yfinance history failed for %s: %s", ticker, exc)
            return []


def _unique_canonical(tickers: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for t in tickers:
        c = canonical_ticker(t)
        if c and c not in seen:
            seen.add(c)
            ordered.append(c)
    return ordered


def _missing_ranges(
    cached_dates: set[_date], start: _date, end: _date
) -> list[tuple[_date, _date]]:
    """Head/tail gaps of ``[start, end]`` not covered by cached dates.

    We cannot distinguish a market holiday from a genuinely-missing trading day, so
    (per the spec) we only fetch the ranges *before* the earliest and *after* the
    latest cached date — extending the cached window rather than probing interior
    gaps that are almost always non-trading days.
    """
    if not cached_dates:
        return [(start, end)]
    min_cached = min(cached_dates)
    max_cached = max(cached_dates)
    ranges: list[tuple[_date, _date]] = []
    if start < min_cached:
        ranges.append((start, min_cached - _ONE_DAY))
    if end > max_cached:
        ranges.append((max_cached + _ONE_DAY, end))
    return ranges


def get_portfolio_tickers(db: Session) -> list[str]:
    """Canonical tickers currently held, from ``position_summary`` (or transactions).

    Prefers the negotiation-summary positions (net qty > 0 when known); falls back
    to distinct transaction tickers when no summary has been imported yet.
    """
    tickers: set[str] = set()

    for ticker, qty_net in db.execute(
        select(PositionSummary.ticker, PositionSummary.qty_net)
    ).all():
        if not ticker:
            continue
        if qty_net is None or qty_net > 0:
            tickers.add(canonical_ticker(ticker))

    if not tickers:
        for (ticker,) in db.execute(select(Transaction.ticker).distinct()).all():
            if ticker:
                tickers.add(canonical_ticker(ticker))

    return sorted(tickers)
