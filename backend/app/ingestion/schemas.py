"""Pydantic response models for the data-ingestion API (task 02).

Subclasses the shared :class:`app.schemas.APIModel` so responses read cleanly from
either dicts or ORM objects.
"""

from __future__ import annotations

from datetime import datetime

from app.schemas import APIModel


class ImportSummary(APIModel):
    """Result of a single ``POST /api/import/{kind}`` upload."""

    kind: str
    rows_imported: int
    tickers: list[str]
    warnings: list[str]


class TableStatus(APIModel):
    """Row count + latest import timestamp for one ingested table."""

    rows: int
    last_imported_at: datetime | None = None


class ImportStatus(APIModel):
    """What data is currently loaded (``GET /api/imports/status``)."""

    transactions: TableStatus
    position_summary: TableStatus
    proventos: TableStatus
