"""Resumo de Negociação importer (sheet ``Negociação - Resumo``).

Reuses ``core.read_negotiation_summary`` for column validation (it raises
``ValueError`` -> HTTP 400 on a malformed file) and maps each row to the
``position_summary`` model shape. Rows whose net quantity is ``<= 0`` are skipped,
matching ``core.get_assets_and_rights``.
"""

from __future__ import annotations

from app.accounting import core  # noqa: F401  (activates repo-root core import + paths)
from app.ingestion.normalize import (
    canonical_ticker,
    clean_str,
    parse_br_date,
    parse_br_number,
)


def parse_summary(file_or_path) -> tuple[list[dict], list[str]]:
    """Return ``(rows, warnings)`` where each row is ``PositionSummary`` kwargs."""
    df = core.read_negotiation_summary(file_or_path)  # raises ValueError on bad columns
    rows: list[dict] = []
    skipped = 0
    for _, row in df.iterrows():
        ticker = canonical_ticker(row.get("Código de Negociação"))
        qty_net = parse_br_number(row.get("Quantidade (Líquida)"))
        if not ticker or qty_net is None or qty_net <= 0:
            skipped += 1
            continue
        rows.append(
            {
                "ticker": ticker,
                "institution": clean_str(row.get("Instituição")),
                "qty_buy": parse_br_number(row.get("Quantidade (Compra)")),
                "qty_sell": parse_br_number(row.get("Quantidade (Venda)")),
                "qty_net": qty_net,
                "avg_price_buy": parse_br_number(row.get("Preço Médio (Compra)")),
                "avg_price_sell": parse_br_number(row.get("Preço Médio (Venda)")),
                "period_start": parse_br_date(row.get("Período (Inicial)")),
                "period_end": parse_br_date(row.get("Período (Final)")),
            }
        )
    warnings: list[str] = []
    if skipped:
        warnings.append(
            f"{skipped} linha(s) ignorada(s) (Quantidade Líquida <= 0 ou sem ticker)."
        )
    return rows, warnings
