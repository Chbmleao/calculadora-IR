# Task 13 — Auto‑update & Refresh (feature #5)

- **Status:** Not started
- **Phase:** Automation
- **Depends on:** 03 (quotes), 04 (positions), 05 (evolution)
- **Size:** M

## Context
Feature #5: values should stay current as prices move and as the investor invests more. Quantities/
cost come from re‑importing B3 exports (task 02); **prices update automatically** from the quote
service (task 03). Since the B3 investor API is unavailable (README §2), "automatic" here means a
scheduled quote refresh + daily snapshot, plus a frictionless re‑import flow — **not** a live
brokerage sync.

## Goal
Keep the dashboard fresh without manual steps: a scheduled job that refreshes quotes and appends a
daily portfolio snapshot, a manual "Refresh now" trigger, and clear "last updated" surfacing — all
within brapi/yfinance free limits via the cache.

## Detailed spec

1. **Refresh service** (`app/jobs/refresh.py`):
   - `refresh_quotes()` → `QuoteService.refresh_latest(get_portfolio_tickers(db))` (task 03).
   - `snapshot_today()` → compute today's portfolio market value + cumulative contributions/proventos
     (reuse task 04/05 logic) and upsert into `snapshots` (task 01). Idempotent per date.
   - `run_daily()` → refresh then snapshot.

2. **Scheduling (MVP‑simple):** use one of, documented in `.env`:
   - APScheduler `BackgroundScheduler` started in `app.main` startup (default; e.g. run `run_daily`
     every N hours on market days), **or**
   - an external cron calling `POST /api/jobs/run-daily`.
   Guard against duplicate same‑day snapshots. Keep request volume within brapi's 15k/mo (cache makes
   this trivial for a single portfolio).

3. **Endpoints** (`app/api/jobs.py`):
   - `POST /api/quotes/refresh` (already in task 03) — manual price refresh.
   - `POST /api/jobs/run-daily` — manual full refresh + snapshot (also the cron target).
   - `GET /api/jobs/status` → `{last_quote_refresh, last_snapshot_date, next_run?}`.

4. **Freshness UI hook:** the header (task 08) shows "Quotes as of <time>" from `GET /api/jobs/status`;
   the global refresh button calls `run-daily` and invalidates positions/evolution queries.

5. **Re‑import flow:** document that when the user buys more, they re‑download the B3 exports and
   re‑upload (task 02 replaces prior rows); evolution/positions recompute on next request. Optionally
   surface a reminder in the UI if the newest transaction is older than N days.

6. **Tests** (`backend/tests/test_refresh.py`): snapshot is idempotent per day; `run_daily` populates
   `snapshots`; scheduler wiring is smoke‑tested (job registered).

## Acceptance criteria
- [ ] A scheduled (or cron‑triggered) `run_daily` refreshes quotes and writes one snapshot/day.
- [ ] Manual "Refresh now" updates prices and the UI reflects a new "as of" time.
- [ ] Re‑importing exports updates quantities and recomputes views.
- [ ] Request volume stays within free‑tier limits (verified via cache hits in tests).

## Out of scope
Live brokerage/B3 API sync (Phase 2). Push notifications/alerts.

## References
Tasks 03/04/05; README §2 (why not B3 API), §7 (env).
