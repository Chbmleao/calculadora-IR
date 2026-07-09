"""Histórico de Negociação importer (sheet ``Negociação``).

There is no ``core.py`` reader for the trade history, so this module reads the
sheet directly and validates the required columns via ``core._check_columns`` (so a
bad file raises the same ``"faltando coluna(s) ..."`` ``ValueError`` -> HTTP 400 as
the other importers). One row per trade; this table is the source for the
evolution reconstruction in task 05.
"""

from __future__ import annotations

import pandas as pd

from app.accounting import core  # activates repo-root core import + paths
from app.ingestion.normalize import (
    canonical_ticker,
    clean_str,
    parse_br_date,
    parse_br_number,
    round_money,
)

SHEET_NAME = "Negociação"
REQUIRED_COLUMNS = [
    "Data do Negócio",
    "Tipo de Movimentação",
    "Mercado",
    "Código de Negociação",
    "Quantidade",
    "Preço",
    "Valor",
    "Instituição",
]
_SIDE_MAP = {"compra": "buy", "venda": "sell"}
_MARKET_MAP = {"mercado à vista": "a_vista", "mercado fracionário": "fracionario"}


def _read(file_or_path):
    try:
        df = pd.read_excel(file_or_path, sheet_name=SHEET_NAME)
    except ValueError:
        # Sheet name absent (older/renamed export) -> fall back to the first sheet.
        if hasattr(file_or_path, "seek"):
            file_or_path.seek(0)
        df = pd.read_excel(file_or_path)
    core._check_columns(df, REQUIRED_COLUMNS, "negociacao.xlsx")
    return df


def parse_transactions(file_or_path) -> tuple[list[dict], list[str]]:
    """Return ``(rows, warnings)`` where each row is ``Transaction`` kwargs."""
    df = _read(file_or_path)  # raises ValueError on bad columns
    rows: list[dict] = []
    skipped = 0
    unknown_sides: set[str] = set()
    unknown_markets: set[str] = set()
    for _, row in df.iterrows():
        ticker = canonical_ticker(row.get("Código de Negociação"))
        trade_date = parse_br_date(row.get("Data do Negócio"))
        if not ticker or trade_date is None:
            skipped += 1
            continue

        raw_side = clean_str(row.get("Tipo de Movimentação")) or ""
        side = _SIDE_MAP.get(raw_side.lower())
        if side is None:
            unknown_sides.add(raw_side)
            side = raw_side.lower()

        raw_market = clean_str(row.get("Mercado")) or ""
        market = _MARKET_MAP.get(raw_market.lower())
        if market is None:
            unknown_markets.add(raw_market)
            market = raw_market.lower()

        rows.append(
            {
                "trade_date": trade_date,
                "ticker": ticker,
                "market": market,
                "side": side,
                "quantity": parse_br_number(row.get("Quantidade")) or 0.0,
                "price": parse_br_number(row.get("Preço")) or 0.0,
                "value": round_money(parse_br_number(row.get("Valor"))) or 0.0,
                "institution": clean_str(row.get("Instituição")),
            }
        )

    warnings: list[str] = []
    if skipped:
        warnings.append(f"{skipped} linha(s) ignorada(s) (sem ticker/data).")
    if unknown_sides:
        warnings.append(
            f"Tipo(s) de movimentação não mapeado(s): {sorted(unknown_sides)}."
        )
    if unknown_markets:
        warnings.append(f"Mercado(s) não mapeado(s): {sorted(unknown_markets)}.")
    return rows, warnings
