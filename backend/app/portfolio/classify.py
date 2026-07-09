"""Asset-class classification for held tickers (task 04).

Maps each canonical ticker to a short **display class** (``ETF`` / ``FII`` / ``BDR``
/ ``Ação``) using the same suffix rules the legacy accounting module applies, and
also exposes the DIRPF *group*/*code* by delegating to ``core.get_product_group`` /
``core.get_product_code`` (reused unchanged via the ``app.accounting`` shim) so the
dashboard never re-implements the tax-declaration taxonomy.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.accounting import core  # noqa: F401  (activates repo-root core import + paths)
from app.quotes.base import canonical_ticker

# ETFs share the "11" suffix with FIIs; these are the ones core.py treats as ETFs.
_ETF_TICKERS = {"IVVB11", "SMAL11"}


@dataclass(frozen=True)
class Classification:
    """A ticker's display class plus its DIRPF group/code (from ``core.py``)."""

    asset_class: str  # display: 'ETF' | 'FII' | 'BDR' | 'Ação'
    dirpf_group: str  # core.get_product_group(...)
    dirpf_code: str  # core.get_product_code(...)


def display_class(ticker: str) -> str:
    """Short display class for a ticker.

    - ends ``11`` and in ``{IVVB11, SMAL11}`` -> ``ETF``
    - other ``11`` -> ``FII``
    - ends ``34`` -> ``BDR``
    - else -> ``Ação``
    """
    t = canonical_ticker(ticker)
    if t.endswith("11"):
        return "ETF" if t in _ETF_TICKERS else "FII"
    if t.endswith("34"):
        return "BDR"
    return "Ação"


def classify(ticker: str) -> Classification:
    """Full classification: display class + DIRPF group/code (reusing ``core.py``)."""
    t = canonical_ticker(ticker)
    return Classification(
        asset_class=display_class(t),
        dirpf_group=core.get_product_group(t),
        dirpf_code=core.get_product_code(t),
    )
