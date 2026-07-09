# Task 06 — Target Allocation & Rebalancing (feature #3)

- **Status:** Not started
- **Phase:** Domain
- **Depends on:** 04 (current positions & weights)
- **Size:** M

## Context
Feature #3: the investor defines a **desired %** per asset (and/or per asset class); the app shows how
far each holding drifts from target and **what to buy** to reach the target. Targets are stored in
`target_allocations` (task 01) and can be seeded from `.env` for the MVP.

## Goal
Endpoints to read/set targets and to compute a rebalancing plan: current vs target weight per
ticker/class, the drift, and suggested buy amounts — including a "contribution mode" that allocates a
new deposit **only via purchases** (no sells), which is what most retail investors want.

## Detailed spec

1. **Targets model & seeding:**
   - Store per‑ticker and/or per‑class targets in `target_allocations` (`kind`, `key`, `target_pct`).
   - Seed from `.env` (`TARGET_ALLOCATIONS` as JSON, e.g. `{"class": {"Ação":40,"FII":30,"ETF":20,"BDR":10}}`)
     on first run if the table is empty. Validate each group sums to ~100% (warn, don't hard‑fail).

2. **Endpoints** (`app/api/targets.py`):
   - `GET /api/targets` → current targets (ticker‑level and class‑level).
   - `PUT /api/targets` → replace targets (body validated; sums checked, warning returned if off).

3. **Rebalancing logic** (`app/portfolio/rebalance.py`), `build_rebalance(db, contribution=0)`:
   - Pull current positions + weights from task 04.
   - For each target key: `target_value = target_pct * (total_market_value + contribution)`;
     `drift_value = target_value - current_value`; `drift_pct = current_weight - target_pct`.
   - **Rebalance‑with‑sells mode** (`contribution=0`): show buy(+)/sell(−) per asset to hit targets.
   - **Contribution mode** (`contribution>0`, default UI mode): distribute the new money to the
     **most underweight** assets first (buys only, never suggest selling). Greedy fill until the
     contribution is exhausted; return suggested `buy_amount` and (using latest price) approximate
     `buy_quantity` per ticker.
   - Support targets defined at class level (split a class target across its tickers proportionally to
     their current holdings, or equally if none) and/or ticker level. Document precedence
     (ticker‑level target overrides class split).

4. **Schema + endpoint:**
   - `GET /api/portfolio/rebalance?contribution=<number>` →
     `{ mode, rows: [{key, kind, current_pct, target_pct, drift_pct, current_value, target_value,
        suggested_buy_amount, suggested_buy_qty, price}], leftover_cash }`.

5. **Tests** (`backend/tests/test_rebalance.py`): with a known portfolio + targets, assert (a)
   contribution mode never emits sells, (b) money goes to the most underweight first, (c) sums of
   suggested buys ≈ contribution (± leftover from indivisible share prices).

## Acceptance criteria
- [ ] Can set and read targets (ticker and/or class level); off‑100% sums return a warning.
- [ ] `rebalance?contribution=1000` suggests buys totaling ~R$1000, prioritizing underweight assets, no sells.
- [ ] Zero‑contribution mode shows the full buy/sell plan to reach targets.
- [ ] Drift per asset is correct vs current weights from task 04.

## Out of scope
UI (task 11); automatic execution/broker integration (never — suggestions only).

## References
Task 04 `PortfolioView`; task 03 prices for share‑quantity conversion; `.env` seeding (README §7).
