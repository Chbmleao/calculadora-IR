"""Foundation smoke tests for task 01.

Covers the acceptance criteria that this layer must satisfy on its own:
- GET /api/health returns {"status": "ok"}
- the SQLite file + all ORM tables are created on startup
- the repo-root core.py is importable and its catalog loads via CATALOG_PATH
- a ValueError from a core.py reader surfaces as HTTP 400 {"error": ...}
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import inspect

from app.api.common import register_exception_handlers
from app.db import engine, init_db
from app.main import app

EXPECTED_TABLES = {
    "transactions",
    "position_summary",
    "proventos",
    "target_allocations",
    "quote_cache",
    "snapshots",
}


def test_health_ok():
    with TestClient(app) as client:
        resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_sqlite_file_and_tables_created():
    # Startup (lifespan) runs create_all; belt-and-suspenders call here too.
    init_db()
    with TestClient(app):
        pass

    db_path = Path(engine.url.database)
    assert db_path.exists(), f"SQLite file not created at {db_path}"

    tables = set(inspect(engine).get_table_names())
    missing = EXPECTED_TABLES - tables
    assert not missing, f"missing tables: {missing}"


def test_core_catalog_importable():
    # The repo-root core.py must be importable from within the backend, and
    # load_catalog() must resolve the xlsx via the configured CATALOG_PATH.
    from core import load_catalog

    catalog = load_catalog()
    assert isinstance(catalog, dict)
    assert catalog, "catalog is empty"
    # Every entry is a ticker -> {Ticker, Tipo, CNPJ} record.
    sample = next(iter(catalog.values()))
    assert "CNPJ" in sample and "Ticker" in sample


def test_value_error_maps_to_http_400():
    # Exercise the real handler + real core.py column check via a throwaway app,
    # so we don't add business routes to the production app.
    import core

    probe = FastAPI()
    register_exception_handlers(probe)

    @probe.get("/boom")
    def boom():
        import pandas as pd

        df = pd.DataFrame({"WrongColumn": [1]})
        # core._check_columns raises ValueError listing the missing columns.
        core._check_columns(df, core.EARNINGS_REQUIRED_COLUMNS, "earnings.xlsx")
        return {"ok": True}  # unreachable

    with TestClient(probe, raise_server_exceptions=False) as client:
        resp = client.get("/boom")

    assert resp.status_code == 400
    body = resp.json()
    assert "error" in body
    assert "faltando" in body["error"]
