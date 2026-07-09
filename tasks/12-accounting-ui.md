# Task 12 — Accounting UI: Bens e Direitos (feature #4)

- **Status:** Not started
- **Phase:** Frontend
- **Depends on:** 07 (accounting API), 08 (scaffold)
- **Size:** S–M

## Context
Ports the existing Streamlit `app.py` flow into the React app, backed by the endpoints from task 07.
This is the IR helper: preview the Bens e Direitos sheet, fill missing CNPJs, and download the `.xlsx`.

## Goal
An `/accounting` page that previews the Bens e Direitos table, flags assets missing a CNPJ with an
inline editor to fill + save them, and offers the `.xlsx` download — mirroring today's Streamlit UX.

## Detailed spec

1. **Preview table:** `GET /api/accounting/bens-e-direitos` → table with the `core` columns (Produto,
   Grupo, Código, CNPJ, Discriminação, Situação final, JCP, Dividendo, Rendimento). Money formatted
   pt‑BR. Show asset count in the header.

2. **Missing‑CNPJ editor:** if `missing_cnpj` is non‑empty, show a warning + an editable list
   (Produto, Grupo read‑only; CNPJ input accepting digits or punctuation). "Salvar no catálogo"
   → `POST /api/accounting/cnpj-overrides` → invalidate the preview so filled CNPJs appear.
   (Mirrors `_missing_cnpj_df` / save flow in `app.py`.)

3. **Download:** button → `GET /api/accounting/bens-e-direitos.xlsx`, triggering a file download named
   `Bens_e_Direitos.xlsx`.

4. **Guidance:** short helper text (reuse the Portuguese copy from `app.py`'s sidebar) explaining which
   B3 exports to import and the period caveat (first purchase → 31/12 of the base year). Link to
   `/import` if data is missing.

5. **States:** empty ("Import your negotiation summary + proventos to generate Bens e Direitos");
   loading; error banner (400s from `core` column validation shown verbatim).

## Acceptance criteria
- [ ] Preview matches the legacy Streamlit output for the same inputs.
- [ ] Missing CNPJs are listed, editable, and persist via `core.save_overrides` (next preview reflects them).
- [ ] `.xlsx` downloads and opens with the standard columns.
- [ ] Empty/loading/error states; pt‑BR formatting.

## Out of scope
New tax calculations (out of scope everywhere in MVP). The reused logic lives in `core.py` (task 07).

## References
Task 07 endpoints; legacy `app.py` (UX to mirror); README §5.
