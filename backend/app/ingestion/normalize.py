"""Normalization helpers for the B3 Excel importers.

Centralizes the conventions from README §7 so every importer normalizes the same
way:

- **Canonical ticker** — uppercase, trailing ``F`` (fractional market) stripped,
  e.g. ``ITSA4F`` -> ``ITSA4``. Mirrors the ``F``-strip ``core.get_assets_and_rights``
  applies, but lives here so it can be reused without re-reading the xlsx.
- **Dates** — B3 exports use ``DD/MM/YYYY``; parsed into :class:`datetime.date`
  (stored ISO by SQLAlchemy). ``"-"`` / blank / ``NaN`` -> ``None``.
- **Numbers** — tolerate pt-BR string formatting (``"1.234,56"``) and the ``"-"``
  placeholder B3 uses for empty numeric cells -> ``None``.
"""

from __future__ import annotations

from datetime import date, datetime

import pandas as pd

REAL_DECIMAL_PLACES = 2
_NULL_TOKENS = {"", "-", "nan", "none", "null"}


def _is_missing(value) -> bool:
    """True for ``None``, float ``NaN``, ``pd.NaT`` / ``pd.NA`` (scalars only)."""
    if value is None:
        return True
    try:
        result = pd.isna(value)
    except (TypeError, ValueError):
        return False
    return bool(result) if isinstance(result, bool) else False


def clean_str(value) -> str | None:
    """Trim to a non-empty string, or ``None`` for missing/blank values."""
    if _is_missing(value):
        return None
    text = str(value).strip()
    return text or None


def canonical_ticker(code) -> str:
    """Uppercase and strip a trailing fractional ``F`` (e.g. ``ITSA4F`` -> ``ITSA4``)."""
    text = "" if _is_missing(code) else str(code).strip().upper()
    if len(text) > 1 and text.endswith("F"):
        text = text[:-1]
    return text


def parse_br_date(value) -> date | None:
    """Parse B3's ``DD/MM/YYYY`` into a :class:`date`; ``"-"``/blank/``NaN`` -> ``None``."""
    if _is_missing(value):
        return None
    if isinstance(value, datetime):  # also catches pandas.Timestamp
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if text.lower() in _NULL_TOKENS:
        return None
    return datetime.strptime(text, "%d/%m/%Y").date()


def parse_br_number(value) -> float | None:
    """Parse a possibly string-formatted number; ``"-"``/blank/``NaN`` -> ``None``.

    Handles pt-BR formatting where ``.`` groups thousands and ``,`` is the decimal
    separator (``"1.234,56"`` -> ``1234.56``). Values that are already numeric are
    returned as ``float`` unchanged.
    """
    if _is_missing(value):
        return None
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if text.lower() in _NULL_TOKENS:
        return None
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".")
    elif "," in text:
        text = text.replace(",", ".")
    text = text.replace("%", "").strip()
    return float(text)


def round_money(value) -> float | None:
    """Round a monetary amount to 2 decimal places (README §7); ``None`` passes through."""
    if value is None:
        return None
    return round(float(value), REAL_DECIMAL_PLACES)
