"""yfinance quote provider (task 03).

yfinance is the **long-history** source and the fallback when brapi is down. B3
tickers map to Yahoo symbols by appending ``.SA`` (``PETR4`` -> ``PETR4.SA``). The
library is unofficial/fragile, so every call is wrapped, retried once with a short
backoff, and an empty frame is treated as a :class:`ProviderError`.

``yfinance`` is imported lazily inside the fetch path so importing this module (and
the FastAPI app) stays cheap and does not require the heavy dependency at import
time. Tests inject ``ticker_factory`` to avoid any network.
"""

from __future__ import annotations

import logging
import time
from datetime import date as _date, timedelta

from app.quotes.base import DailyClose, ProviderError, Quote, canonical_ticker, to_money

logger = logging.getLogger(__name__)

# How far back to look when deriving a "latest" price from daily history — a week
# comfortably covers weekends + a holiday so we still find the last real close.
_LATEST_LOOKBACK_DAYS = 7


class YFinanceProvider:
    """Daily closes (and derived latest prices) from Yahoo Finance via yfinance."""

    name = "yfinance"

    def __init__(
        self,
        *,
        timeout: float = 10.0,
        retries: int = 1,
        backoff: float = 0.5,
        ticker_factory=None,
    ):
        self.timeout = timeout
        self.retries = retries
        self.backoff = backoff
        # Injectable for tests; defaults to a real yfinance.Ticker (imported lazily).
        self._ticker_factory = ticker_factory

    def _symbol(self, ticker: str) -> str:
        return f"{canonical_ticker(ticker)}.SA"

    def _make_ticker(self, symbol: str):
        if self._ticker_factory is not None:
            return self._ticker_factory(symbol)
        import yfinance  # lazy: heavy import only when actually fetching

        return yfinance.Ticker(symbol)

    def _fetch_frame(self, symbol: str, start: _date, end: _date):
        """Call ``Ticker.history`` with one retry; return a pandas DataFrame."""
        # yfinance treats ``end`` as exclusive, so extend by a day to include it.
        params = dict(
            start=start.isoformat(),
            end=(end + timedelta(days=1)).isoformat(),
            interval="1d",
            auto_adjust=False,
        )
        attempts = self.retries + 1
        last_exc: Exception | None = None
        for attempt in range(attempts):
            try:
                ticker = self._make_ticker(symbol)
                try:
                    return ticker.history(timeout=self.timeout, **params)
                except TypeError:
                    # Some yfinance versions/stubs don't accept ``timeout``.
                    return ticker.history(**params)
            except Exception as exc:  # noqa: BLE001 — yfinance raises broad errors
                last_exc = exc
                if attempt < attempts - 1:
                    time.sleep(self.backoff * (attempt + 1))
        raise ProviderError(
            f"yfinance fetch failed for {symbol}: {last_exc}", provider=self.name
        ) from last_exc

    def history(self, ticker: str, start: _date, end: _date) -> list[DailyClose]:
        symbol = self._symbol(ticker)
        frame = self._fetch_frame(symbol, start, end)
        if frame is None or getattr(frame, "empty", True):
            raise ProviderError(f"yfinance returned no rows for {symbol}", provider=self.name)
        if "Close" not in frame.columns:
            raise ProviderError(f"yfinance frame missing Close for {symbol}", provider=self.name)

        out: list[DailyClose] = []
        for index, close in frame["Close"].items():
            day = _to_date(index)
            if day is None or close is None:
                continue
            # Skip NaN closes (yfinance emits them for gaps/half-days).
            if close != close:  # noqa: PLR0124 — NaN check without importing math
                continue
            if start <= day <= end:
                out.append(DailyClose(date=day, close=to_money(close)))
        out.sort(key=lambda dc: dc.date)
        return out

    def latest(self, tickers: list[str]) -> dict[str, Quote]:
        """Derive a latest price per ticker from the most recent daily close.

        Never raises for a single ticker: an unresolved symbol is simply skipped.
        """
        end = _date.today()
        start = end - timedelta(days=_LATEST_LOOKBACK_DAYS)
        out: dict[str, Quote] = {}
        for ticker in tickers:
            canon = canonical_ticker(ticker)
            if not canon or canon in out:
                continue
            try:
                rows = self.history(canon, start, end)
            except ProviderError as exc:
                logger.warning("yfinance latest miss for %s: %s", canon, exc)
                continue
            if not rows:
                continue
            last = rows[-1]
            out[canon] = Quote(price=last.close, date=last.date, source=self.name)
        return out


def _to_date(index) -> _date | None:
    """Coerce a pandas Timestamp / datetime / date index label to a date."""
    to_date = getattr(index, "date", None)
    if callable(to_date):  # pandas Timestamp / datetime.datetime
        return to_date()
    if isinstance(index, _date):  # plain datetime.date (no .date() method)
        return index
    return None
