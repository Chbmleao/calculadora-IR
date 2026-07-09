"""Proventos Recebidos importer (sheet ``Proventos Recebidos``).

Reuses ``core.read_earnings`` for column validation, then persists **every** event
type to ``proventos`` (the accounting-relevant subset is noted in
``ACCOUNTING_EVENT_TYPES`` for later filtering, but nothing is dropped here). The
ticker is taken from the ``Produto`` column (``"CMIG4 - CIA..."`` -> ``CMIG4``).
Trailer/total rows (blank ``Produto``) are skipped.
"""

from __future__ import annotations

from app.accounting import core  # activates repo-root core import + paths
from app.ingestion.normalize import (
    canonical_ticker,
    clean_str,
    parse_br_date,
    parse_br_number,
    round_money,
)

# The IR-relevant subset (README §4). Kept for downstream filtering — the importer
# stores all event types.
ACCOUNTING_EVENT_TYPES = frozenset(
    {"Rendimento", "Juros Sobre Capital Próprio", "Dividendo"}
)


def parse_proventos(file_or_path) -> tuple[list[dict], list[str]]:
    """Return ``(rows, warnings)`` where each row is ``Provento`` kwargs."""
    df = core.read_earnings(file_or_path)  # raises ValueError on bad columns
    rows: list[dict] = []
    skipped = 0
    for _, row in df.iterrows():
        produto = clean_str(row.get("Produto"))
        if not produto:  # trailer/"Total" rows have an empty Produto cell
            skipped += 1
            continue
        rows.append(
            {
                "ticker": canonical_ticker(produto.split(" - ")[0]),
                "pay_date": parse_br_date(row.get("Pagamento")),
                "event_type": clean_str(row.get("Tipo de Evento")) or "",
                "institution": clean_str(row.get("Instituição")),
                "quantity": parse_br_number(row.get("Quantidade")),
                "unit_price": parse_br_number(row.get("Preço unitário")),
                "net_value": round_money(parse_br_number(row.get("Valor líquido"))),
            }
        )
    warnings: list[str] = []
    if skipped:
        warnings.append(f"{skipped} linha(s) ignorada(s) (sem Produto).")
    return rows, warnings
