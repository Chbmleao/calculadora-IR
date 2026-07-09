# Task 11 — Rebalancing UI: Targets & Buy Suggestions (feature #3)

- **Status:** Not started
- **Phase:** Frontend
- **Depends on:** 06 (targets + rebalance API), 08 (scaffold)
- **Size:** M

## Context
Renders and edits targets (`GET/PUT /api/targets`) and shows the rebalancing plan
(`GET /api/portfolio/rebalance?contribution=`) from task 06. The primary use case: "I have R$X to
invest this month — what should I buy to move toward my target allocation?"

## Goal
A `/rebalance` page where the investor edits desired % per asset/class, enters a contribution amount,
and sees current vs target weights, drift, and concrete buy suggestions (amount + approx share qty).

## Detailed spec

1. **Targets editor:** table of `key` (ticker or class) with an editable `target_pct` input; a live
   running total that flags when the group doesn't sum to 100%. Save via `PUT /api/targets`
   (mutation → invalidate rebalance query). Allow toggling between class‑level and ticker‑level view
   if both exist.

2. **Contribution input:** a currency field ("Aporte") that drives
   `GET /api/portfolio/rebalance?contribution=`. Default to contribution mode (buys only).

3. **Rebalance table:** columns — Asset, Current %, Target %, **Drift %** (bar, red if overweight /
   green if underweight), Current value, Suggested buy (R$), Suggested qty (shares). Sort by drift.
   Show `leftover_cash` (unallocated due to indivisible share prices).

4. **Current‑vs‑target visual:** a grouped bar or diverging bar per asset (current vs target weight).
   Follow the `dataviz` skill.

5. **States:** empty ("Set your target allocation to get buy suggestions"); loading; error. If targets
   sum ≠ 100%, show an inline warning but still compute.

## Acceptance criteria
- [ ] Can edit + save targets; running total flags non‑100% sums.
- [ ] Entering a contribution shows buy suggestions summing ≈ contribution, prioritizing underweight assets, no sells.
- [ ] Drift per asset visualized; leftover cash shown.
- [ ] Empty/loading/error states; pt‑BR formatting; light/dark legible.

## Out of scope
Rebalance math (task 06); order execution (never — suggestions only).

## References
Task 06 endpoints/schema; task 08 hooks/format; `dataviz` skill.
