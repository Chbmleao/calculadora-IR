# Task 02 — Data Ingestion (Excel importers + catalog + upload)

- **Status:** Not started
- **Phase:** Data
- **Depends on:** 01 (models, DB, core import)
- **Size:** M

## Context
The app's inputs are the four B3 Excel exports described in `tasks/README.md` §4 (real samples in
`input/` and `data/`). This task reads them, normalizes, and persists to the SQLite tables from
task 01, **reusing `core.py` readers where they exist**. It also exposes an upload endpoint so the
frontend can import files. Column names are authoritative — match them exactly.

## Goal
Given the three uploadable exports (Resumo de Negociação, histórico de Negociação, Proventos), parse
and persist them into `position_summary`, `transactions`, and `proventos`; expose the catalog; and
provide an idempotent import that replaces prior rows of the same type.

## Detailed spec

1. **Normalization helpers** (`app/ingestion/normalize.py`):
   - `canonical_ticker(code) -> str`: uppercase, strip trailing `F` (fractional). (`core.py` already
     does the `F` strip in `get_assets_and_rights`; centralize it here and reuse.)
   - `parse_br_date("DD/MM/YYYY") -> date` (return `None` for `"-"`).
   - `parse_br_number` for values that may arrive as strings.

2. **Resumo de Negociação** (`app/ingestion/positions.py`) — sheet `Negociação - Resumo`:
   - Reuse `core.read_negotiation_summary(file)` (validates required columns, raises `ValueError`).
   - Map columns → `position_summary`: `Código de Negociação`→ticker (canonicalized),
     `Instituição`, `Quantidade (Compra/Venda/Líquida)`, `Preço Médio (Compra/Venda)`,
     `Período (Inicial/Final)`. Skip rows with `Quantidade (Líquida) <= 0` (matches `core.py`).

3. **Histórico de Negociação** (`app/ingestion/transactions.py`) — sheet `Negociação`:
   - Required columns: `Data do Negócio`, `Tipo de Movimentação`, `Mercado`,
     `Código de Negociação`, `Quantidade`, `Preço`, `Valor`, `Instituição`.
   - Map `Tipo de Movimentação`: `Compra`→`buy`, `Venda`→`sell`. Map `Mercado`:
     `Mercado à Vista`→`a_vista`, `Mercado Fracionário`→`fracionario`.
   - Canonicalize ticker; parse date. One row per trade. **This is the source for evolution (task 05).**

4. **Proventos** (`app/ingestion/proventos.py`) — sheet `Proventos Recebidos`:
   - Reuse `core.read_earnings(file)` for validation. Persist rows to `proventos`, canonicalizing the
     ticker from `Produto` (`"CMIG4 - CIA..."` → split on `" - "`, take first token → canonicalize).
   - Keep **all** event types in the DB, but note the accounting‑relevant subset
     (`Rendimento`, `Juros Sobre Capital Próprio`, `Dividendo`) for later filtering.

5. **Catalog** (`app/ingestion/catalog.py`): thin wrapper exposing `core.load_catalog()` (ticker →
   `{Tipo, CNPJ}`) so other modules can resolve asset type/CNPJ without re‑reading the xlsx.

6. **Import service** (`app/ingestion/service.py`): `import_file(kind, file_bytes, filename)` where
   `kind ∈ {positions, transactions, proventos}`. **Idempotent:** delete existing rows of that kind
   before inserting (single‑user MVP — a re‑upload fully replaces). Return a summary
   `{kind, rows_imported, tickers, warnings}`.
   - **Preserve manual entries:** for `transactions`, the delete step must be scoped to
     `origin='import'` only, so manually-entered trades (task 02b, `origin='manual'`) survive
     re-imports. Set `origin='import'` and `source_file=filename` on imported rows.

7. **Endpoints** (`app/api/imports.py`):
   - `POST /api/import/{kind}` (multipart file) → import summary. 400 on `ValueError` (bad columns).
   - `GET /api/imports/status` → row counts + last `imported_at` per table (so the UI can show what's loaded).

8. **Tests** (`backend/tests/test_ingestion.py`): run each importer against the real sample files in
   `input/` and assert row counts/known tickers (e.g. `AAPL34`, `IVVB11` present; fractional `BBSE3F`
   canonicalized to `BBSE3`).

## Acceptance criteria
- [ ] Uploading each sample file persists the expected rows; re‑uploading replaces, not duplicates.
- [ ] Fractional tickers are canonicalized (`ITSA4F`→`ITSA4`); dates stored ISO.
- [ ] Bad file (missing column) → HTTP 400 `{"error": "...faltando coluna(s)..."}`.
- [ ] `GET /api/imports/status` reflects loaded data.
- [ ] Tests pass against real `input/` samples.

## Out of scope
Quotes/valuation (task 03/04), evolution math (task 05), accounting output (task 07).

## References
`core.read_negotiation_summary`, `core.read_earnings`, `core.load_catalog`; README §4–§5;
samples: `input/negotiation_summary.xlsx`, `input/negociacao-*.xlsx`, `input/earnings.xlsx`.
