# Task 05 — Patrimony Evolution & Rentability (feature #2)

- **Status:** Not started
- **Phase:** Domain
- **Depends on:** 02 (transactions), 03 (historical quotes)
- **Size:** L (core value of the product)

## Context
Feature #2: chart total patrimony over time and show **true rentability** — separating money the
investor *added* (contributions) from *market gains*. The `transactions` table (task 02, from the
B3 *histórico* export) has **per‑trade dates, quantity, price, and side**, so we can reconstruct the
holdings on any past date; combined with historical daily closes (task 03, yfinance for long history)
we build a daily equity curve. This is the decided approach: **full historical reconstruction**.

## Goal
An endpoint returning a daily (or configurable‑granularity) time series of portfolio market value,
cumulative contributions, cumulative proventos, and return metrics (simple return, time‑weighted
return that removes contribution timing effects, and optionally money‑weighted/XIRR).

## Detailed spec

1. **Holdings timeline** (`app/portfolio/evolution.py`):
   - Sort `transactions` by `trade_date`. Walk forward maintaining `holdings[ticker] = quantity`
     (`buy` adds, `sell` subtracts). Record the running quantity per ticker after each event.
   - Determine the series start = first `trade_date`; end = today (or last available quote date).

2. **Historical prices:** for each held ticker, fetch daily closes over `[start, end]` via task 03
   (delta‑cached). Build a per‑ticker price map by date; **forward‑fill** missing days
   (weekends/holidays/gaps) using the last known close.

3. **Daily valuation:** for each calendar day `d` in `[start, end]`:
   - `holdings_d` = quantities as of `d` (from the timeline).
   - `market_value_d = Σ holdings_d[t] * price_d[t]` (skip tickers with no price yet → treat as cost
     or 0 and flag; document the choice).
   - `contributions_d` = cumulative net cash invested up to `d` = Σ (buy `value`) − Σ (sell `value`).
   - `proventos_d` = cumulative `net_value` from `proventos` with `pay_date ≤ d`.

4. **Return metrics** (`app/portfolio/returns.py`):
   - **Simple return** = `(market_value + cumulative_proventos - contributions) / contributions`.
   - **Time‑weighted return (TWR):** chain daily sub‑period returns, neutralizing the cash flow on
     contribution days: `r_d = (V_d - F_d) / V_{d-1} - 1` where `F_d` is the net flow on day `d`;
     `TWR = Π(1 + r_d) - 1`. This is the headline "rentabilidade" figure.
   - **(Optional) money‑weighted / XIRR** from dated cash flows (contributions as negative, current
     value as positive) using Newton's method — mark optional if time‑constrained.

5. **Caching:** persist computed daily points into `snapshots` (task 01) so re‑requests are cheap;
   recompute only from the last cached date forward, and fully recompute when new transactions are
   imported (task 02 should bump a "data version" the evolution service checks).

6. **Schema + endpoint** (`app/api/portfolio.py`):
   - `GET /api/portfolio/evolution?granularity=daily|weekly|monthly&from=&to=` →
     `{ points: [{date, market_value, contributions, proventos, invested_cost}],
        metrics: {simple_return, twr, xirr?, absolute_gain}, as_of }`.
   - Granularity down‑samples the daily series (e.g. month‑end points).

7. **Tests** (`backend/tests/test_evolution.py`): construct a tiny synthetic transaction set +
   deterministic price series; assert holdings reconstruction at key dates, that a pure contribution
   with flat prices yields ~0% TWR (but rising `market_value`), and that a price rise with no flows
   yields TWR = price change %.

## Acceptance criteria
- [ ] Endpoint returns a dated series of patrimony, contributions, and proventos from first trade → today.
- [ ] Adding cash does **not** inflate TWR (contributions separated from market gains).
- [ ] Reconstructed holdings on a past date match a hand‑checked example.
- [ ] Series computed from cache on repeat calls; recomputes after a new import.
- [ ] Granularity switch works (daily/weekly/monthly).

## Out of scope
UI/chart (task 10), rebalancing (task 06), scheduled snapshots (task 13 — this task computes on demand).

## References
`transactions` schema (README §4), task 03 `history()`, task 02 import versioning.
