# Task 02b — Manual Trade Entry (optional; extends Task 02)

- **Status:** Not started
- **Phase:** Data (optional add-on)
- **Depends on:** 01 (models), 02 (ingestion); consumed by 04 (positions) & 05 (evolution)
- **Size:** M

## Context
Even B3's *official, paid* portfolio sync (used by StatusInvest/Kinvo/Gorila) only returns ~the last
**18 months** of history and requires older trades to be **entered manually** — so manual entry is a
standard, expected complement to imports, not a workaround. For our app it serves two real needs:
1. **Incremental updates** — after you buy/sell, log the trade without re-downloading the whole B3
   export.
2. **Backfilling** — add older trades the exports don't cover.

Manual trades and imported trades live in the **same `transactions` table**; they are distinguished by
an `origin` flag so a re-import never destroys manual rows (see the amendments below).

## Goal
Backend CRUD for manually-entered trades (marked `origin='manual'`) plus a small UI form + editable
list, such that manual trades correctly feed both the evolution series (task 05) and the current
positions view (task 04), and survive re-imports of the B3 files.

## Required amendments to existing tasks (do these as part of this task if not already done)
- **Task 01 (`transactions` model):** add `origin STR('import'|'manual')` (default `'import'`) and an
  optional `note STR`. `source_file` stays NULL for manual rows.
- **Task 02 (idempotent import):** the "delete existing rows before inserting" step must delete **only
  `origin='import'`** rows for that kind. Manual rows (`origin='manual'`) are preserved across re-imports.
- **Task 04 (positions):** current positions must reflect manual trades layered on top of the imported
  `position_summary` baseline (see "Positions interaction" below).

## Detailed spec

1. **Validation model** (`app/schemas.py` `TradeInput`): `trade_date` (≤ today), `ticker`
   (canonicalized via task 02 `canonical_ticker`), `side` (`buy`/`sell`), `quantity` (>0),
   `price` (>0), optional `market` (default `a_vista`), optional `institution`, optional `note`.
   Compute `value = quantity * price`. Reject a `sell` that exceeds current net quantity for the
   ticker (return 400 with a clear message).

2. **CRUD endpoints** (`app/api/trades.py`):
   - `POST /api/trades` → create a manual trade (`origin='manual'`). Returns the created row.
   - `GET /api/trades?origin=manual|import|all` → list (default `manual`), newest first.
   - `PATCH /api/trades/{id}` → edit a **manual** trade (reject edits to `origin='import'` rows → 409).
   - `DELETE /api/trades/{id}` → delete a **manual** trade only.
   - Each mutation bumps the "data version" (task 05) so positions/evolution recompute.

3. **Positions interaction (the important part):** `position_summary` is B3's authoritative baseline
   (net qty + cumulative avg cost, correct up to its `period_end`). Manual trades represent activity
   the baseline doesn't yet include. In task 04's `build_positions`, after loading the baseline:
   - Apply manual `transactions` with `trade_date > position_summary.period_end` (for that ticker;
     if the ticker has no baseline row, start from zero).
   - **Buy:** `new_qty = qty + q`; `new_avg = (qty*avg + q*price) / new_qty` (weighted average cost).
   - **Sell:** `new_qty = qty - q`; keep `avg` unchanged (avg cost method).
   - Tickers that reach `qty <= 0` drop out (consistent with `core.py`).
   Document this "baseline + manual delta since period_end" rule in code comments. (Evolution/task 05
   needs no special handling — it already walks the full `transactions` table, manual rows included.)

4. **Staleness hint:** `GET /api/imports/status` (task 02) should also report the count of manual
   trades and the latest manual `trade_date`, so the UI can nudge "you have unsynced manual trades —
   consider re-importing your B3 export to reconcile."

5. **UI** (extend the `/import` page from task 08, or a sibling `/trades` view):
   - An **"Adicionar operação"** form (ticker autocomplete from held tickers + free entry; date;
     buy/sell; qty; price; live-computed total). Submit → `POST /api/trades`, invalidate
     positions/evolution/imports-status queries.
   - A **list of manual trades** with inline edit + delete (imported trades shown read-only if listed).
   - Clear messaging that manual trades layer on top of the last B3 import and are preserved across
     re-imports.

6. **Reconciliation note (UX copy):** when the user re-imports a fresh B3 export whose `period_end` is
   now newer than some manual trades, those manual trades are effectively superseded by the baseline.
   MVP behavior: keep them but stop applying any with `trade_date <= new period_end` (the baseline
   already includes them). Surface a one-click "clear superseded manual trades" action. Document this.

## Acceptance criteria
- [ ] Can add/edit/delete a manual trade; imported trades are not editable/deletable via these endpoints.
- [ ] A re-import (task 02) preserves `origin='manual'` rows and only replaces `origin='import'` rows.
- [ ] A manual buy after the last import date updates the **positions** view (qty + weighted avg cost)
      and the **evolution** series; a manual sell reduces quantity.
- [ ] Selling more than held is rejected with a clear 400.
- [ ] Superseded manual trades (dated ≤ a newer import's period_end) stop double-counting; the
      "clear superseded" action works.
- [ ] Tests cover: origin-scoped re-import delete, weighted-avg recompute on manual buy, evolution
      inclusion, superseded handling.

## Out of scope
Manual proventos entry (possible future add-on — this task is trades only). Broker/API auto-sync (Phase 2).

## References
Tasks 01 (model), 02 (idempotent import), 04 (positions baseline), 05 (evolution/data-version);
StatusInvest/B3 ~18-month history limitation (see `tasks/README.md` §2 rationale).
