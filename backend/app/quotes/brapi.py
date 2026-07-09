"""brapi.dev quote provider (task 03).

brapi speaks native B3 tickers (``PETR4``, ``MXRF11``, ``AAPL34``) and is the
primary source for current/recent quotes. Free tier: ~15k req/mo and ~1 year of
history, so ``history`` requests one ticker at a time with ``range=1y``.

The token is sent both as a ``token`` query param and an ``Authorization: Bearer``
header (brapi accepts either). Auth/limit/not-found responses (401/403/404/429)
become :class:`ProviderError` so the service falls back to yfinance.
"""

from __future__ import annotations

from datetime import date as _date, datetime, timezone

import httpx

from app.quotes.base import DailyClose, ProviderError, Quote, canonical_ticker, to_money

# HTTP statuses that mean "this provider can't serve you right now" -> fall back.
_FALLBACK_STATUSES = {401, 402, 403, 404, 429}


class BrapiProvider:
    """Fetches latest quotes and ~1y daily history from brapi.dev."""

    name = "brapi"

    def __init__(
        self,
        base_url: str,
        token: str = "",
        *,
        timeout: float = 10.0,
        client: httpx.Client | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.token = (token or "").strip()
        self.timeout = timeout
        # A caller (or test) may inject a client; otherwise build a default one.
        self._client = client or httpx.Client(timeout=timeout)

    # -- HTTP plumbing -----------------------------------------------------

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    def _params(self, extra: dict | None = None) -> dict:
        params = dict(extra or {})
        if self.token:
            params["token"] = self.token
        return params

    def _get(self, path: str, params: dict | None = None) -> dict:
        url = f"{self.base_url}{path}"
        try:
            resp = self._client.get(url, params=self._params(params), headers=self._headers())
        except httpx.HTTPError as exc:  # network/timeout
            raise ProviderError(f"brapi request failed: {exc}", provider=self.name) from exc

        status = resp.status_code
        if status in _FALLBACK_STATUSES:
            raise ProviderError(
                f"brapi returned HTTP {status} for {path}", provider=self.name, status_code=status
            )
        if status >= 400:
            raise ProviderError(
                f"brapi returned HTTP {status} for {path}", provider=self.name, status_code=status
            )
        try:
            return resp.json()
        except ValueError as exc:
            raise ProviderError("brapi returned non-JSON body", provider=self.name) from exc

    # -- Public API --------------------------------------------------------

    def latest(self, tickers: list[str]) -> dict[str, Quote]:
        canon = _unique_canonical(tickers)
        if not canon:
            return {}
        data = self._get(f"/quote/{','.join(canon)}")
        results = data.get("results") or []
        out: dict[str, Quote] = {}
        for row in results:
            symbol = row.get("symbol")
            price = row.get("regularMarketPrice")
            if symbol is None or price is None:
                continue
            qdate = _parse_market_time(row.get("regularMarketTime"))
            key = canonical_ticker(symbol)
            out[key] = Quote(price=to_money(price), date=qdate, source=self.name)
        return out

    def history(self, ticker: str, start: _date, end: _date) -> list[DailyClose]:
        canon = canonical_ticker(ticker)
        data = self._get(f"/quote/{canon}", {"range": "1y", "interval": "1d"})
        results = data.get("results") or []
        if not results:
            raise ProviderError(f"brapi has no results for {canon}", provider=self.name)
        hist = results[0].get("historicalDataPrice") or []
        out: list[DailyClose] = []
        for row in hist:
            epoch = row.get("date")
            close = row.get("close")
            if epoch is None or close is None:
                continue
            day = datetime.fromtimestamp(int(epoch), tz=timezone.utc).date()
            if start <= day <= end:
                out.append(DailyClose(date=day, close=to_money(close)))
        out.sort(key=lambda dc: dc.date)
        return out


def _unique_canonical(tickers: list[str]) -> list[str]:
    """Canonicalize + dedupe, preserving first-seen order."""
    seen: set[str] = set()
    ordered: list[str] = []
    for t in tickers:
        c = canonical_ticker(t)
        if c and c not in seen:
            seen.add(c)
            ordered.append(c)
    return ordered


def _parse_market_time(value) -> _date:
    """Parse brapi's ``regularMarketTime`` (ISO-8601 string or epoch) to a date.

    Falls back to today's UTC date when absent/unparseable — a latest quote is
    always "as of now" enough for cache keying.
    """
    if value is None:
        return datetime.now(timezone.utc).date()
    # Epoch seconds (int or numeric string).
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(int(value), tz=timezone.utc).date()
    text = str(value).strip()
    if text.isdigit():
        return datetime.fromtimestamp(int(text), tz=timezone.utc).date()
    try:
        # Normalize a trailing ``Z`` which fromisoformat rejects on older stdlib.
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return datetime.now(timezone.utc).date()
