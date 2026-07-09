# Task 07 — Accounting: Bens e Direitos (feature #4, reuse core.py)

- **Status:** Not started
- **Phase:** Domain
- **Depends on:** 02 (proventos + catalog available)
- **Size:** S

## Context
Feature #4 is the **existing** IR feature: generate the DIRPF "Bens e Direitos" sheet. The logic
already lives in `core.py` (`get_assets_and_rights`, `build_output_xlsx_bytes`, classification, CNPJ
lookup, discrimination text) and today runs via `app.py` (Streamlit) and `calculator.py` (CLI). This
task exposes that **unchanged** logic through the FastAPI backend so the React UI can preview and
download it. **Do not rewrite the tax rules.**

## Goal
Backend endpoints that: build the Bens e Direitos preview from the imported Resumo de Negociação +
Proventos + catalog, return it as JSON for preview, generate the downloadable `.xlsx`, list assets
with missing CNPJ, and save CNPJ overrides — mirroring the current Streamlit flow (`app.py`).

## Detailed spec

1. **Wrapper** (`app/accounting/service.py`) importing from repo‑root `core`:
   - `build_assets(db_or_files)`: obtain the earnings map via `core.get_earnings(...)`, the negotiation
     DataFrame via `core.read_negotiation_summary(...)`, catalog via `core.load_catalog()`, then call
     `core.get_assets_and_rights(negotiation, earnings, catalog)`. Prefer reading from the **already
     imported** data (task 02); if the accounting logic needs the original DataFrames, re‑read the
     stored source files or reconstruct the expected frames. Document which path is used.
   - `build_xlsx()` → `core.build_output_xlsx_bytes(assets)`.
   - `missing_cnpj(assets)` → list of `{Produto, Grupo}` where `CNPJ == "Não encontrado"`
     (mirror `_missing_cnpj_df` in `app.py`).
   - `save_cnpj(rows)` → `core.save_overrides(rows)` then invalidate the catalog cache.

2. **Endpoints** (`app/api/accounting.py`):
   - `GET /api/accounting/bens-e-direitos` → `{ assets: [...], missing_cnpj: [...] }` (JSON preview;
     same columns `core` produces: Produto, Grupo, Código, CNPJ, Discriminação, Situação final, JCP,
     Dividendo, Rendimento).
   - `GET /api/accounting/bens-e-direitos.xlsx` → streamed `.xlsx`
     (`application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`), filename `Bens_e_Direitos.xlsx`.
   - `POST /api/accounting/cnpj-overrides` (body: `[{Ticker, Tipo, CNPJ}]`) → saves via
     `core.save_overrides`, returns count saved.

3. **Reuse, don't fork:** import the existing functions; the only new code is the HTTP layer + reading
   from imported data instead of file uploads. Keep `app.py`/`calculator.py` working.

4. **Tests** (`backend/tests/test_accounting.py`): run against the real `input/` samples; assert the
   asset list matches what `calculator.py` produces for the same inputs (e.g. same count, same
   Situação final for a known ticker), and that the `.xlsx` bytes open and contain the expected columns.

## Acceptance criteria
- [ ] `GET /api/accounting/bens-e-direitos` returns the same rows the current `core` logic produces.
- [ ] `.xlsx` download opens in Excel with the standard Bens e Direitos columns.
- [ ] Missing‑CNPJ assets are listed; saving an override persists via `core.save_overrides` and the
      next preview reflects it.
- [ ] `core.py` is imported, not reimplemented; legacy `app.py`/CLI still run.

## Out of scope
New tax calculations (capital‑gains tax, isentos) — same scope caveat as the current README.
UI (task 12).

## References
`core.get_assets_and_rights`, `core.build_output_xlsx_bytes`, `core.save_overrides`; `app.py`
(the flow to mirror); README §5.
