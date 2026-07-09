# Task 04 — Positions & Allocation (feature #1)

- **Status:** Not started
- **Phase:** Domain
- **Depends on:** 02 (holdings), 03 (quotes)
- **Size:** M

## Context
Feature #1: show current holdings, their market value, and the **% weight** of each asset and each
asset class. Quantities + cost basis come from `position_summary` (task 02); current prices from the
quote service (task 03); asset class from the catalog + suffix rules in `core.py`
(`get_product_group` / `get_product_code`).

## Goal
An endpoint returning, per held ticker: quantity, average cost, invested amount, current price,
current market value, unrealized P/L (value − cost) and %, portfolio weight %, asset class, and
accumulated proventos; plus portfolio totals and an asset‑class allocation breakdown.

## Detailed spec

1. **Asset class** (`app/portfolio/classify.py`): map each ticker to a display class using the same
   logic as `core.get_product_group`/`get_product_code`:
   - ends `11` and in `{IVVB11, SMAL11}` → `ETF`; other `11` → `FII`; ends `34` → `BDR`; else → `Ação`.
   Return both the display class and the DIRPF group/code (reuse `core.py`).

2. **Positions builder** (`app/portfolio/positions.py`), `build_positions(db) -> PortfolioView`:
   - **Baseline + manual delta:** `position_summary` is the authoritative baseline. If manual trades
     exist (task 02b, `origin='manual'`), apply those dated **after** the summary's `period_end` on top
     of the baseline per ticker — buy → recompute weighted avg cost `(qty*avg + q*price)/(qty+q)`;
     sell → reduce qty, keep avg; drop tickers reaching `qty <= 0`. (If task 02b isn't built, this is a
     no-op and positions come purely from the summary.)
   - For each resulting position with `qty_net > 0`:
     - `invested = qty_net * avg_price_buy`
     - `price = latest[ticker].price` (from task 03; may be `None` if unresolved → mark `stale`)
     - `market_value = qty_net * price`
     - `pnl = market_value - invested`, `pnl_pct = pnl / invested`
     - `proventos_total` = sum of `net_value` for that ticker (accounting subset from task 02)
   - Totals: `total_invested`, `total_market_value`, `total_pnl`, `total_proventos`.
   - Per‑ticker `weight_pct = market_value / total_market_value`.
   - Class allocation: group by asset class → `{class, market_value, weight_pct}`.

3. **Schema** (`app/schemas.py`): `Position` and `PortfolioView`
   ```
   Position: ticker, asset_class, quantity, avg_price, invested, price, price_date,
             market_value, pnl, pnl_pct, weight_pct, proventos_total, stale(bool)
   PortfolioView: as_of, totals{invested, market_value, pnl, pnl_pct, proventos},
                  positions[Position], allocation_by_class[{asset_class, market_value, weight_pct}]
   ```

4. **Endpoint** (`app/api/portfolio.py`): `GET /api/portfolio/positions` → `PortfolioView`.
   - If no holdings imported → empty view with a clear message field (not a 500).
   - Include `stale: true` per position when the price could not be fetched (uses last cached close if
     available, else invested value as a fallback and `stale=true`).

5. **Tests** (`backend/tests/test_positions.py`): with sample `position_summary` + mocked quotes,
   assert weights sum to ~100%, class grouping is correct, and a missing price yields `stale=true`
   without crashing.

## Acceptance criteria
- [ ] `GET /api/portfolio/positions` returns per‑ticker value, weight %, P/L, and class allocation.
- [ ] Weights sum to 100% (± rounding); class breakdown matches per‑ticker sums.
- [ ] Proventos per ticker included.
- [ ] Missing quote → `stale=true`, no crash.

## Out of scope
Time series/evolution (task 05), targets/rebalancing (task 06), UI (task 09).

## References
`core.get_product_group/get_product_code`; tasks 02 & 03; README §4–§5.
