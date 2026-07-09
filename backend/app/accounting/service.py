"""Accounting service — the "Bens e Direitos" (DIRPF) domain layer (task 07).

This is a **thin wrapper** over the repo-root ``core.py`` tax logic. It does NOT
re-implement any tax rule: it reuses ``core.get_assets_and_rights``,
``core.get_earnings``, ``core.build_output_xlsx_bytes``, ``core.load_catalog`` and
``core.save_overrides`` unchanged (see README §5). The only new behaviour is
sourcing the inputs from the **already-imported** database (task 02) instead of the
raw uploaded xlsx files.

DATA-SOURCE PATH (documented per the task spec)
-----------------------------------------------
``core.get_assets_and_rights(negotiation_df, earnings_map, catalog)`` expects two
pandas frames. Rather than re-reading the original uploads (which are gitignored and
may be gone), we **reconstruct the exact frames core expects** from the persisted
rows:

* ``position_summary`` -> the "Negociação - Resumo" frame (columns
  ``Código de Negociação``, ``Instituição``, ``Quantidade (Líquida)``,
  ``Preço Médio (Compra)``). Tickers are already canonical (uppercase, trailing
  ``F`` stripped), which is exactly what ``get_assets_and_rights`` would produce
  after its own ``F``-strip — so the output is identical either way.
* ``proventos`` -> the "Proventos Recebidos" frame (columns ``Tipo de Evento``,
  ``Produto``, ``Valor líquido``) fed through ``core.get_earnings`` to obtain the
  same ``{ticker: {Rendimento, Juros Sobre Capital Próprio, Dividendo}}`` map.

The catalog is loaded once and cached; ``save_cnpj`` clears that cache after writing
overrides so the next preview reflects them (mirrors ``app.py``'s
``st.cache_data.clear()``).
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.accounting import core  # activates repo-root core import + configured paths
from app.models import PositionSummary, Provento

# Columns core.get_assets_and_rights reads from the negotiation frame.
_NEGOTIATION_COLUMNS = [
    "Código de Negociação",
    "Instituição",
    "Quantidade (Líquida)",
    "Preço Médio (Compra)",
]
# Columns core.get_earnings reads from the proventos frame.
_EARNINGS_COLUMNS = ["Tipo de Evento", "Produto", "Valor líquido"]

_CNPJ_NOT_FOUND = "Não encontrado"


@lru_cache(maxsize=1)
def _catalog_cached() -> dict:
    """Process-wide cached ``ticker -> {Tipo, CNPJ, Ticker}`` catalog.

    Cleared by :func:`save_cnpj` after new overrides are written.
    """
    return core.load_catalog()


def _to_float(value) -> float:
    """Coerce a DB Numeric/None into a plain float (None -> 0.0)."""
    return float(value) if value is not None else 0.0


def _negotiation_frame(db: Session) -> pd.DataFrame:
    """Rebuild the "Negociação - Resumo" frame from ``position_summary`` rows."""
    rows = db.execute(select(PositionSummary)).scalars().all()
    records = [
        {
            "Código de Negociação": p.ticker,
            "Instituição": p.institution or "",
            "Quantidade (Líquida)": _to_float(p.qty_net),
            "Preço Médio (Compra)": _to_float(p.avg_price_buy),
        }
        for p in rows
    ]
    return pd.DataFrame(records, columns=_NEGOTIATION_COLUMNS)


def _earnings_map(db: Session) -> dict:
    """Rebuild the earnings map via ``core.get_earnings`` from ``proventos`` rows."""
    rows = db.execute(select(Provento)).scalars().all()
    if not rows:
        return {}
    records = [
        {
            "Tipo de Evento": p.event_type or "",
            "Produto": p.ticker,
            "Valor líquido": _to_float(p.net_value),
        }
        for p in rows
    ]
    frame = pd.DataFrame(records, columns=_EARNINGS_COLUMNS)
    return core.get_earnings(frame)


def build_assets(db: Session) -> list[dict[str, Any]]:
    """Build the Bens e Direitos rows from imported data via ``core`` (unchanged).

    Returns the exact dicts ``core.get_assets_and_rights`` produces (keys: Produto,
    Grupo, Código, CNPJ, Discriminação, Situação final, Juros Sobre Capital Próprio,
    Dividendo, Rendimento).
    """
    negotiation = _negotiation_frame(db)
    earnings = _earnings_map(db)
    catalog = _catalog_cached()
    return core.get_assets_and_rights(negotiation, earnings, catalog)


def build_xlsx(assets: list[dict[str, Any]]) -> bytes:
    """Serialize the asset rows to ``.xlsx`` bytes via ``core`` (unchanged)."""
    return core.build_output_xlsx_bytes(assets)


def missing_cnpj(assets: list[dict[str, Any]]) -> list[dict[str, str]]:
    """List ``{Produto, Grupo}`` for assets missing a catalog CNPJ.

    Mirrors ``_missing_cnpj_df`` in ``app.py``.
    """
    return [
        {"Produto": a["Produto"], "Grupo": a["Grupo"]}
        for a in assets
        if a["CNPJ"] == _CNPJ_NOT_FOUND
    ]


def save_cnpj(rows: list[dict[str, Any]]) -> int:
    """Persist CNPJ overrides via ``core.save_overrides`` and invalidate the cache.

    ``rows`` is an iterable of dicts with keys ``Ticker``, ``Tipo`` (optional) and
    ``CNPJ``. Rows with a blank CNPJ are dropped (matching ``app.py``). Returns the
    number of rows saved.
    """
    normalized = [
        {
            "Ticker": r["Ticker"],
            "Tipo": r.get("Tipo") or "",
            "CNPJ": str(r.get("CNPJ", "")).strip(),
        }
        for r in rows
        if str(r.get("CNPJ", "")).strip()
    ]
    core.save_overrides(normalized)
    _catalog_cached.cache_clear()  # next preview re-reads the catalog with overrides
    return len(normalized)
