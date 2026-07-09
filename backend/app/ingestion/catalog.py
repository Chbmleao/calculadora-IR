"""Thin wrapper over ``core.load_catalog`` (ticker -> ``{Ticker, Tipo, CNPJ}``).

Lets other layers resolve an asset's type / CNPJ without re-reading the catalog
xlsx themselves. Importing ``core`` from ``app.accounting`` guarantees the repo-root
module is on ``sys.path`` and its ``CATALOG_PATH`` points at the configured file.
"""

from __future__ import annotations

from app.accounting import core
from app.ingestion.normalize import canonical_ticker


def load_catalog() -> dict:
    """Return the full ``ticker -> {Ticker, Tipo, CNPJ}`` catalog."""
    return core.load_catalog()


def resolve(ticker: str) -> dict | None:
    """Look up a catalog record, falling back to the canonical ticker form."""
    catalog = load_catalog()
    if ticker in catalog:
        return catalog[ticker]
    return catalog.get(canonical_ticker(ticker))
