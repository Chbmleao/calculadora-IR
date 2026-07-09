# Task 09 — Dashboard UI: Positions & Allocation (feature #1)

- **Status:** Not started
- **Phase:** Frontend
- **Depends on:** 04 (positions API), 08 (scaffold)
- **Size:** M

## Context
The landing page. Consumes `GET /api/portfolio/positions` (task 04) and renders the portfolio at a
glance: KPIs, an allocation donut, and a positions table. Follow the `dataviz` skill before writing
chart code.

## Goal
A `/` Dashboard that shows total patrimony, invested, P/L, and proventos as KPI tiles; an allocation
donut by asset class (with % labels); and a sortable positions table with per‑asset weight and P/L.

## Detailed spec

1. **KPI row** (`StatTile`s): Total market value, Total invested, Unrealized P/L (value + %, colored
   green/red), Proventos received. Use `formatBRL`/`formatPct`. Show the "as of" date.

2. **Allocation donut** (Recharts `PieChart`): slices = `allocation_by_class`
   (Ação / FII / ETF / BDR), labeled with class + weight %. A legend lists each class value. Use the
   `dataviz` palette (categorical, colorblind‑safe, light/dark aware).

3. **Positions table:** columns — Ticker, Class, Qty, Avg price, Invested, Price (+ date/stale badge),
   Market value, P/L (R$ + %), **Weight %**. Sortable by weight/value/P/L. Highlight `stale` rows
   (price could not be refreshed). A small inline bar for weight % is a nice touch.

4. **States:** loading skeleton; empty state ("Import your B3 negotiation summary to see positions"
   linking to `/import`); error banner on API failure.

5. **Refresh:** the global "Refresh quotes" button (from task 08) invalidates the positions query on
   success so values update without reload.

## Acceptance criteria
- [ ] KPIs, donut, and table render from live `GET /api/portfolio/positions`.
- [ ] Donut % and table weights are consistent and sum to ~100%.
- [ ] Stale prices are visually flagged; empty/loading/error states handled.
- [ ] Money/%/dates use the pt‑BR formatters; light/dark both legible.

## Out of scope
Time series (task 10), targets (task 11). Read‑only page.

## References
Task 04 `PortfolioView`; task 08 hooks/format; `dataviz` skill.
