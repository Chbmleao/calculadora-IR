# Task 03 — Quote Service (brapi + yfinance + SQLite cache)

- **Status:** Not started
- **Phase:** Data
- **Depends on:** 01 (config, `quote_cache` model)
- **Size:** M

## Context
B3 exports carry cost basis and quantities but **no market prices**. The B3 investor API is
institutionally gated and is not a quote feed (see README §2), so prices come from public sources.
Strategy: **brapi.dev** for current/recent quotes (native B3 tickers, free 15k req/mo, 1‑yr history),
**yfinance** (`.SA` suffix) for multi‑year history and as a fallback, and a **SQLite cache** of daily
closes to cut request volume and survive outages. Everything sits behind a provider interface so
brapi Pro or another source can be swapped in via config.

## Goal
A `QuoteService` that returns (a) the latest price for a set of tickers and (b) a historical daily
close series for a ticker over a date range — cached in `quote_cache`, resilient to a provider being
down, and covering ações, FIIs, ETFs, and BDRs.

## Detailed spec

1. **Provider interface** (`app/quotes/base.py`):
   ```python
   class QuoteProvider(Protocol):
       def latest(self, tickers: list[str]) -> dict[str, Quote]: ...      # Quote: price, date, source
       def history(self, ticker: str, start: date, end: date) -> list[DailyClose]: ...
   ```
   `DailyClose = {date, close}`.

2. **brapi provider** (`app/quotes/brapi.py`):
   - Latest: `GET {BRAPI_BASE_URL}/quote/{TICKERS}?token=...` (comma‑joined). Parse
     `results[].regularMarketPrice` + `regularMarketTime`.
   - History: `GET /quote/{TICKER}?range=1y&interval=1d&token=...` → `results[0].historicalDataPrice[]`
     (`date` epoch, `close`). Free tier ⇒ range capped at ~1y; request 1 ticker at a time.
   - Send `Authorization: Bearer <BRAPI_TOKEN>` when set. Handle 401/429/404 by raising a typed
     `ProviderError` (so the service can fall back).

3. **yfinance provider** (`app/quotes/yfinance_provider.py`):
   - Map ticker → `f"{ticker}.SA"`. Use `yfinance.Ticker(sym).history(start=, end=, interval="1d")`
     (or `download`). Extract `Close` per date. This is the **long‑history** source.
   - Wrap in try/except; empty result ⇒ `ProviderError`. Add a short timeout + one retry w/ backoff.

4. **Cache** (`app/quotes/cache.py`): read/write `quote_cache (ticker,date,close,source,fetched_at)`.
   - `get_cached_history(ticker, start, end)` and `upsert(rows)`.
   - Treat a cached latest quote as fresh if `fetched_at` within `QUOTE_CACHE_TTL_MINUTES`.

5. **Service** (`app/quotes/service.py`):
   - `latest(tickers)`: return cached fresh quotes; for the rest, try brapi → on error/miss try
     yfinance → cache results. Never raise for a single missing ticker; return what resolved and log
     misses.
   - `history(ticker, start, end)`: serve from cache; fetch only **missing date ranges** (delta
     fetch); for ranges older than brapi's free window, use yfinance; merge + cache. Weekends/holidays
     have no close — forward‑fill is the *consumer's* job (task 05), not the cache's.
   - `refresh_latest(tickers)`: force‑refresh (used by task 13).

6. **Ticker universe:** derive the set of held tickers from `position_summary` / `transactions`
   (task 02). Provide `get_portfolio_tickers(db)`.

7. **Endpoints** (`app/api/quotes.py`):
   - `GET /api/quotes/latest` → `{ticker: {price, date, source}}` for held tickers.
   - `POST /api/quotes/refresh` → refresh + return count updated.
   - (History is consumed internally by task 05; no public endpoint required.)

8. **Tests** (`backend/tests/test_quotes.py`): mock HTTP (brapi) and yfinance; assert fallback path,
   cache hit avoids network, delta fetch only requests missing dates. Include one **opt‑in**
   integration test (skipped by default, enabled via env) that hits brapi for a known ticker.

## Acceptance criteria
- [ ] `latest()` returns prices for a mix of ação/FII/ETF/BDR (`PETR4`, `MXRF11`, `IVVB11`, `AAPL34`).
- [ ] brapi failure transparently falls back to yfinance; a single unknown ticker doesn't crash the batch.
- [ ] Second call for the same day serves from cache (no network) within TTL.
- [ ] History delta‑fetches only missing dates and persists them.
- [ ] Unit tests pass with mocked providers; integration test skipped unless enabled.

## Out of scope
Portfolio valuation and %s (task 04); evolution reconstruction/forward‑fill (task 05); scheduling (task 13).

## References
README §2 (quote strategy), brapi docs `https://brapi.dev/docs`, yfinance `.SA` tickers.
