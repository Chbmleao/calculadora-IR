# Task 01 — Backend Foundation (FastAPI + config + SQLite + conventions)

- **Status:** Not started
- **Phase:** Foundations
- **Depends on:** 00 (scaffold)
- **Size:** M

## Context
We are adding a Python **FastAPI** backend under `backend/` that will reuse the repo‑root `core.py`
accounting logic and add importers, a quote service, and portfolio math. Persistence is a single
**SQLite** file. Read `tasks/README.md` §3–§7 first. This task creates the app skeleton, settings,
DB engine + ORM models, response conventions, and a health check that everything else builds on.

## Goal
A runnable FastAPI app (`uvicorn app.main:app`) that: loads config from `.env`, opens a SQLite DB,
creates all tables on startup, exposes `GET /api/health`, and has CORS enabled for the frontend dev
origin. No business endpoints yet — just the foundation the other tasks plug into.

## Detailed spec

1. **Dependencies** (`backend/requirements.txt` or `pyproject.toml`): `fastapi`, `uvicorn[standard]`,
   `pydantic>=2`, `pydantic-settings`, `sqlalchemy>=2`, `pandas>=2`, `openpyxl>=3.1`, `httpx`,
   `yfinance`, `python-dotenv`, `pytest`. (`pandas`/`openpyxl` already used by `core.py`.)

2. **Config** (`app/config.py`) via `pydantic-settings`, read from `.env`:
   - `DATABASE_URL` (default `sqlite:///./data/app.db`)
   - `BRAPI_TOKEN` (optional; empty ⇒ use tokenless/yfinance)
   - `BRAPI_BASE_URL` (default `https://brapi.dev/api`)
   - `CORS_ORIGINS` (default `http://localhost:5173`)
   - `CATALOG_PATH` (default `../data/b3_enterprises.xlsx` — reuse the existing catalog)
   - `QUOTE_CACHE_TTL_MINUTES` (default `60`)
   Provide a cached `get_settings()`.

3. **DB layer** (`app/db.py`): SQLAlchemy 2.0 engine + `SessionLocal` + a `get_db()` FastAPI
   dependency (yield/close). `create_all()` on startup. Ensure `backend/data/` exists.

4. **ORM models** (`app/models.py`) — these tables serve tasks 02–13. Use the exact fields below
   (canonical ticker = uppercase, no trailing `F`):

   - `transactions` — one row per trade (from the *histórico* export **or** manual entry, task 02b):
     `id PK, trade_date DATE, ticker STR, market STR('a_vista'|'fracionario'), side STR('buy'|'sell'),
      quantity NUM, price NUM, value NUM, institution STR, origin STR('import'|'manual') default 'import',
      note STR NULL, source_file STR NULL, imported_at DATETIME`
     (`origin` lets re-imports replace only imported rows while preserving manual ones — see task 02b.)
   - `position_summary` — one row per ticker (from the *Resumo* export):
     `id PK, ticker STR, institution STR, qty_buy NUM, qty_sell NUM, qty_net NUM,
      avg_price_buy NUM, avg_price_sell NUM, period_start DATE, period_end DATE, imported_at DATETIME`
   - `proventos` — income events (from the *Proventos* export):
     `id PK, ticker STR, pay_date DATE, event_type STR, institution STR, quantity NUM,
      unit_price NUM, net_value NUM, source_file STR, imported_at DATETIME`
   - `target_allocations` — desired weights (task 06):
     `id PK, kind STR('ticker'|'class'), key STR, target_pct NUM` (unique on (kind,key))
   - `quote_cache` — daily closes (task 03):
     `ticker STR, date DATE, close NUM, source STR, fetched_at DATETIME` (PK (ticker,date))
   - `snapshots` — cached equity‑curve points (tasks 05/13):
     `date DATE PK, total_value NUM, total_cost NUM, contributions_to_date NUM,
      cumulative_proventos NUM, computed_at DATETIME`

   > **CNPJ overrides stay in the existing xlsx** (`core.save_overrides`) for accounting
   > compatibility — do **not** move them into the DB.

5. **Response conventions** (`app/api/common.py`):
   - Success → the Pydantic model / list directly.
   - Errors → `HTTPException` producing `{"error": "<message>"}`. Add an exception handler mapping
     `ValueError` (raised by `core.py` `_check_columns`) → HTTP 400 with the message.
   - All money fields serialized as numbers rounded to 2dp.

6. **App wiring** (`app/main.py`): create `FastAPI(title="Investment Dashboard API")`, add
   `CORSMiddleware` from `CORS_ORIGINS`, startup hook to create tables, include routers (empty for
   now), and `GET /api/health` → `{"status":"ok"}`.

7. **Import `core.py`:** the backend must import the repo‑root module. Make it importable (e.g. add
   the repo root to `sys.path` in `app/accounting/__init__.py`, or install the root as editable).
   Document the chosen approach in a top comment.

## Acceptance criteria
- [ ] `uvicorn app.main:app --reload` starts; `GET /api/health` returns `{"status":"ok"}`.
- [ ] SQLite file is created with all tables on first run.
- [ ] `from core import load_catalog` works from within the backend and returns the catalog.
- [ ] `.env.example` updated with every setting above.
- [ ] A ValueError from a `core.py` reader surfaces as HTTP 400 `{"error": ...}`.
- [ ] `pytest` runs (even if only a health test) and passes.

## Out of scope
Business endpoints, quotes, importers (their own tasks). Auth (none in MVP).

## References
`core.py` (functions to import), `tasks/README.md` §3–§7, sample data in `input/` and `data/`.
