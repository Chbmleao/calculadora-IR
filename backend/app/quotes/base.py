"""Quote provider interface + shared value objects (task 03).

Providers (brapi, yfinance) implement :class:`QuoteProvider`. The service layer
programs against this Protocol so a new source can be dropped in via config. All
providers raise :class:`ProviderError` on failure so the service can fall back to
the next source instead of crashing.

Money is normalized to 2dp (`README §7`); tickers are canonicalized to uppercase
with a trailing fractional ``F`` stripped (matching ``core.get_assets_and_rights``).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as _date
from decimal import Decimal, ROUND_HALF_UP
from typing import Protocol, runtime_checkable

_MONEY = Decimal("0.01")


def to_money(value) -> Decimal:
    """Coerce any numeric (float / int / str / Decimal / numpy) to a 2dp Decimal.

    Goes through ``str`` so binary-float noise (e.g. ``33.449999``) does not leak
    into the quantized result.
    """
    if isinstance(value, Decimal):
        dec = value
    else:
        dec = Decimal(str(value))
    return dec.quantize(_MONEY, rounding=ROUND_HALF_UP)


def canonical_ticker(ticker: str) -> str:
    """Canonical ticker: uppercase, trailing fractional ``F`` stripped.

    Mirrors the normalization in the legacy ``core.py`` (``ITSA4F`` -> ``ITSA4``).
    """
    t = (ticker or "").strip().upper()
    if len(t) > 1 and t.endswith("F"):
        t = t[:-1]
    return t


class ProviderError(Exception):
    """A quote provider failed (HTTP error, rate limit, empty result, ...).

    Carrying the provider name + optional HTTP status makes fallbacks and logs
    legible without leaking provider internals to callers.
    """

    def __init__(self, message: str, *, provider: str | None = None, status_code: int | None = None):
        super().__init__(message)
        self.provider = provider
        self.status_code = status_code


@dataclass(frozen=True)
class Quote:
    """A single latest price for a ticker."""

    price: Decimal
    date: _date
    source: str


@dataclass(frozen=True)
class DailyClose:
    """One daily close in a historical series."""

    date: _date
    close: Decimal


@runtime_checkable
class QuoteProvider(Protocol):
    """The contract every quote source implements."""

    name: str

    def latest(self, tickers: list[str]) -> dict[str, Quote]:
        """Return the latest price per (canonical) ticker; may omit unresolved ones."""
        ...

    def history(self, ticker: str, start: _date, end: _date) -> list[DailyClose]:
        """Return daily closes for ``ticker`` within ``[start, end]`` (inclusive)."""
        ...
