"""Task 02 — data-ingestion tests, run against the real B3 samples in ``input/``.

These exercise the importer functions and the persistence service **directly**
(no FastAPI app / TestClient) so they can run while sibling feature routers are
still mid-write. Endpoint wiring is covered by the coordinator's app-level suite.

Sample files live in the repo-root ``input/`` folder (gitignored). Override the
location with ``INGESTION_SAMPLES_DIR`` if needed.
"""

from __future__ import annotations

import io
import os
from datetime import date
from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.ingestion import positions, proventos, service, transactions
from app.ingestion.normalize import (
    canonical_ticker,
    parse_br_date,
    parse_br_number,
    round_money,
)
from app.models import Base, PositionSummary, Provento, Transaction

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SAMPLES_DIR = Path(os.environ.get("INGESTION_SAMPLES_DIR", _REPO_ROOT / "input"))

SUMMARY_FILE = "negotiation_summary.xlsx"
HISTORICO_GLOB = "negociacao-*.xlsx"
EARNINGS_FILE = "earnings.xlsx"


def _sample_bytes(pattern: str) -> bytes:
    matches = sorted(_SAMPLES_DIR.glob(pattern))
    if not matches:
        pytest.skip(f"sample matching '{pattern}' not found in {_SAMPLES_DIR}")
    return matches[0].read_bytes()


def _buf(pattern: str) -> io.BytesIO:
    return io.BytesIO(_sample_bytes(pattern))


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, future=True)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _count(db, model, *where) -> int:
    stmt = select(func.count()).select_from(model)
    for clause in where:
        stmt = stmt.where(clause)
    return db.execute(stmt).scalar_one()


# --- normalization helpers -----------------------------------------------------


def test_canonical_ticker_strips_fractional_f():
    assert canonical_ticker("bbse3f") == "BBSE3"
    assert canonical_ticker("ITSA4F") == "ITSA4"
    assert canonical_ticker(" aapl34 ") == "AAPL34"
    # Trailing '11' (FII/ETF) must not be mangled; non-'F' unchanged.
    assert canonical_ticker("IVVB11") == "IVVB11"
    assert canonical_ticker("CMIG4") == "CMIG4"


def test_parse_br_date():
    assert parse_br_date("22/10/2020") == date(2020, 10, 22)
    assert parse_br_date("-") is None
    assert parse_br_date(None) is None
    assert parse_br_date("") is None


def test_parse_br_number():
    assert parse_br_number("1.234,56") == 1234.56
    assert parse_br_number("34,86") == 34.86
    assert parse_br_number("234") == 234.0
    assert parse_br_number(64.67) == 64.67
    assert parse_br_number("-") is None
    assert parse_br_number(None) is None
    assert round_money(49.084) == 49.08
    assert round_money(None) is None


# --- parsing real samples ------------------------------------------------------


def test_parse_positions_sample():
    rows, warnings = positions.parse_summary(_buf(SUMMARY_FILE))
    tickers = {r["ticker"] for r in rows}
    assert len(rows) == 20
    assert {"AAPL34", "IVVB11", "SMAL11", "BBSE3"} <= tickers
    # Fractional BBSE3F canonicalized away.
    assert "BBSE3F" not in tickers
    # AAPL34 is still open: Período (Final) '-' -> None; Período (Inicial) parsed.
    aapl = next(r for r in rows if r["ticker"] == "AAPL34")
    assert aapl["period_end"] is None
    assert aapl["period_start"] == date(2020, 10, 22)
    assert isinstance(warnings, list)


def test_parse_transactions_sample():
    rows, warnings = transactions.parse_transactions(_buf(HISTORICO_GLOB))
    assert len(rows) == 175
    assert all(r["side"] in {"buy", "sell"} for r in rows)
    assert all(r["market"] in {"a_vista", "fracionario"} for r in rows)
    assert all(isinstance(r["trade_date"], date) for r in rows)
    # ITSA4F trades are canonicalized to ITSA4.
    assert "ITSA4" in {r["ticker"] for r in rows}


def test_parse_proventos_sample_keeps_all_event_types():
    rows, warnings = proventos.parse_proventos(_buf(EARNINGS_FILE))
    # 115 sheet rows minus the 3 trailer/"Total" rows with blank Produto.
    assert len(rows) == 112
    tickers = {r["ticker"] for r in rows}
    assert "CMIG4" in tickers
    event_types = {r["event_type"] for r in rows}
    # Accounting subset AND non-accounting events are both retained.
    assert {"Dividendo", "Juros Sobre Capital Próprio"} <= event_types
    assert "Reembolso" in event_types


# --- persistence service (idempotent replace) ----------------------------------


def test_import_positions_replaces_not_duplicates(db):
    data = _sample_bytes(SUMMARY_FILE)
    summary = service.import_file(db, "positions", data, SUMMARY_FILE)
    assert summary["kind"] == "positions"
    assert summary["rows_imported"] == 20
    assert "AAPL34" in summary["tickers"]
    assert _count(db, PositionSummary) == 20

    # Re-upload fully replaces — count stays 20, not 40.
    service.import_file(db, "positions", data, SUMMARY_FILE)
    assert _count(db, PositionSummary) == 20


def test_import_transactions_preserves_manual_rows(db):
    # A manually-entered trade (task 02b) that must survive re-imports.
    db.add(
        Transaction(
            trade_date=date(2025, 1, 1),
            ticker="PETR4",
            market="a_vista",
            side="buy",
            quantity=10,
            price=30,
            value=300,
            origin="manual",
        )
    )
    db.commit()

    data = _sample_bytes(HISTORICO_GLOB)
    service.import_file(db, "transactions", data, "hist.xlsx")
    assert _count(db, Transaction, Transaction.origin == "import") == 175
    assert _count(db, Transaction, Transaction.origin == "manual") == 1

    # Re-import: imported rows replaced, the manual row still there.
    service.import_file(db, "transactions", data, "hist.xlsx")
    assert _count(db, Transaction, Transaction.origin == "import") == 175
    assert _count(db, Transaction, Transaction.origin == "manual") == 1

    imported_row = db.execute(
        select(Transaction).where(Transaction.origin == "import")
    ).scalars().first()
    assert imported_row.source_file == "hist.xlsx"


def test_import_proventos(db):
    summary = service.import_file(
        db, "proventos", _sample_bytes(EARNINGS_FILE), "earnings.xlsx"
    )
    assert summary["rows_imported"] == 112
    assert _count(db, Provento) == 112


def test_bad_file_raises_value_error_and_leaves_db_untouched(db):
    bad = io.BytesIO()
    pd.DataFrame({"WrongColumn": [1, 2]}).to_excel(bad, index=False)
    with pytest.raises(ValueError) as exc:
        service.import_file(db, "proventos", bad.getvalue(), "bad.xlsx")
    assert "faltando" in str(exc.value)
    # Parse failed before any delete/insert.
    assert _count(db, Provento) == 0


def test_invalid_kind_raises_value_error(db):
    with pytest.raises(ValueError):
        service.import_file(db, "nonsense", b"whatever", "x.xlsx")


def test_import_status_reflects_loaded_data(db):
    before = service.import_status(db)
    assert before["position_summary"]["rows"] == 0
    assert before["position_summary"]["last_imported_at"] is None

    service.import_file(db, "positions", _sample_bytes(SUMMARY_FILE), SUMMARY_FILE)
    after = service.import_status(db)
    assert after["position_summary"]["rows"] == 20
    assert after["position_summary"]["last_imported_at"] is not None
    assert after["transactions"]["rows"] == 0
