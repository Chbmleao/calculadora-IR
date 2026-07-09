# Backend — Investment Dashboard API (FastAPI)

FastAPI service that powers the React dashboard. Reuses the repo-root `core.py` (Bens e Direitos
logic) and adds Excel ingestion, a quote service (brapi + yfinance + SQLite cache), portfolio math,
and a SQLite store. See `../tasks/` for the full spec.

## Run

```bash
pip install -r requirements.txt
cp ../.env.example ../.env        # then edit values
uvicorn app.main:app --reload --port 8000
```

Health check: `GET http://localhost:8000/api/health`.

## Layout

```
app/
  main.py        # FastAPI app + router wiring + startup (create tables)
  config.py      # settings from .env (pydantic-settings)
  db.py          # SQLite engine/session + get_db dependency
  models.py      # ORM tables
  schemas.py     # Pydantic response models
  ingestion/     # Excel importers (wrap core.py readers)
  quotes/        # brapi + yfinance providers + cache
  portfolio/     # positions, evolution, rebalancing
  accounting/    # thin wrapper over core.py
  jobs/          # scheduled refresh + snapshot
  api/           # route modules per domain
tests/           # pytest, runs against the real sample files in ../input/
```

## Tests

```bash
pytest -q
```
