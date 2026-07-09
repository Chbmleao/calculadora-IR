# Task 10 — Evolution UI: Patrimony & Rentability (feature #2)

- **Status:** Not started
- **Phase:** Frontend
- **Depends on:** 05 (evolution API), 08 (scaffold)
- **Size:** M

## Context
Renders `GET /api/portfolio/evolution` (task 05): the patrimony curve over time plus rentability
metrics that separate contributions from market gains. Read the `dataviz` skill first.

## Goal
An `/evolution` page with a time‑series chart of patrimony vs cumulative contributions (so the gap =
market gains), proventos over time, headline return metrics, and a granularity/period selector.

## Detailed spec

1. **Main chart** (Recharts `AreaChart`/`LineChart`): x = date; series = **Patrimony (market value)**
   and **Contributions (cumulative)**. The shaded gap between them visualizes market gain/loss. Tooltip
   shows date, patrimony, contributions, and gain. Optionally a third line for cumulative proventos.

2. **Metric tiles:** Simple return %, **TWR %** (headline "rentabilidade"), absolute gain (R$), and
   XIRR % if provided. Color by sign. Add a one‑line tooltip explaining TWR ("return excluding the
   effect of deposits/withdrawals").

3. **Controls:** granularity toggle (Daily / Weekly / Monthly) and period presets (YTD, 1Y, All) →
   drive the `granularity` / `from` / `to` query params.

4. **Performance:** for long daily series, prefer monthly/weekly by default and let the user drill in;
   memoize the chart data transform.

5. **States:** loading skeleton; empty state ("Import your trade history to reconstruct your patrimony
   evolution" → `/import`); error banner.

## Acceptance criteria
- [ ] Chart shows patrimony vs contributions over time from live data; gap reads as market gain/loss.
- [ ] TWR and simple return tiles render and match the API metrics.
- [ ] Granularity + period controls update the chart via query params.
- [ ] Empty/loading/error states handled; pt‑BR formatting; light/dark legible.

## Out of scope
The return math (task 05 owns it — this page only visualizes).

## References
Task 05 evolution schema; task 08 hooks/format; `dataviz` skill (time‑series guidance).
