"""Import orchestration: parse a B3 export and persist it idempotently.

``import_file`` dispatches on ``kind`` to the right parser, then **replaces** the
prior rows of that kind (single-user MVP — a re-upload fully replaces, never
duplicates). Parsing happens *before* any delete, so a malformed file raises
``ValueError`` (-> HTTP 400) and leaves the database untouched.

Idempotency detail: for ``transactions`` the delete is scoped to
``origin='import'`` so manually-entered trades (task 02b, ``origin='manual'``)
survive re-imports.
"""

from __future__ import annotations

from io import BytesIO

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.ingestion import positions, proventos, transactions
from app.models import PositionSummary, Provento, Transaction

VALID_KINDS = ("positions", "transactions", "proventos")


def import_file(
    db: Session, kind: str, file_bytes: bytes, filename: str | None = None
) -> dict:
    """Parse and persist one uploaded export; return an import summary dict."""
    if kind not in VALID_KINDS:
        raise ValueError(
            f"Tipo de importação inválido: '{kind}'. Use um de {list(VALID_KINDS)}."
        )

    buffer = BytesIO(file_bytes)
    if kind == "positions":
        rows, warnings = positions.parse_summary(buffer)
        _replace_positions(db, rows)
    elif kind == "transactions":
        rows, warnings = transactions.parse_transactions(buffer)
        _replace_transactions(db, rows, filename)
    else:  # proventos
        rows, warnings = proventos.parse_proventos(buffer)
        _replace_proventos(db, rows, filename)

    db.commit()
    tickers = sorted({r["ticker"] for r in rows if r.get("ticker")})
    return {
        "kind": kind,
        "rows_imported": len(rows),
        "tickers": tickers,
        "warnings": warnings,
    }


def import_status(db: Session) -> dict:
    """Row counts + latest ``imported_at`` per ingested table."""
    return {
        "transactions": _table_status(db, Transaction, Transaction.imported_at),
        "position_summary": _table_status(
            db, PositionSummary, PositionSummary.imported_at
        ),
        "proventos": _table_status(db, Provento, Provento.imported_at),
    }


# --- persistence helpers -------------------------------------------------------


def _replace_positions(db: Session, rows: list[dict]) -> None:
    db.execute(delete(PositionSummary))
    db.add_all([PositionSummary(**row) for row in rows])


def _replace_transactions(
    db: Session, rows: list[dict], filename: str | None
) -> None:
    # Scope delete to imported rows so manual entries (task 02b) survive.
    db.execute(delete(Transaction).where(Transaction.origin == "import"))
    db.add_all(
        [Transaction(origin="import", source_file=filename, **row) for row in rows]
    )


def _replace_proventos(db: Session, rows: list[dict], filename: str | None) -> None:
    db.execute(delete(Provento))
    db.add_all([Provento(source_file=filename, **row) for row in rows])


def _table_status(db: Session, model, imported_at_col) -> dict:
    count = db.execute(select(func.count()).select_from(model)).scalar_one()
    last = db.execute(select(func.max(imported_at_col))).scalar_one()
    return {"rows": int(count or 0), "last_imported_at": last}
