"""Return metrics for the patrimony evolution curve (task 05).

Pure functions over the daily equity-curve points produced by
:mod:`app.portfolio.evolution` — no DB, no network — so they are trivially
unit-testable with a synthetic series.

Three headline figures (README §7):

* **Simple return** — ``(market_value + proventos - contributions) / contributions``.
  Naive "how much more is it worth than I put in", *inflated* by contribution timing.
* **Time-weighted return (TWR)** — chains daily sub-period returns, neutralizing the
  cash flow on each contribution day so adding money never shows up as "gain". This
  is the headline *rentabilidade*.
* **Money-weighted return (XIRR)** — the internal rate of return of the dated cash
  flows (contributions out, proventos + final value in), solved with Newton's method.
  Optional: ``None`` when it cannot be resolved.

Money stays in :class:`~decimal.Decimal`; unitless ratios are returned as ``float``
rounded to 6 dp.
"""

from __future__ import annotations

from datetime import date as _date
from decimal import Decimal

from app.quotes.base import to_money

_ZERO = Decimal("0")
_RATIO_DP = 6


def _round_ratio(value: float) -> float:
    return round(value, _RATIO_DP)


def simple_return(
    market_value: Decimal, cumulative_proventos: Decimal, contributions: Decimal
) -> float | None:
    """``(V + proventos - contributions) / contributions``; ``None`` if no money in."""
    if contributions <= _ZERO:
        return None
    gain = Decimal(market_value) + Decimal(cumulative_proventos) - Decimal(contributions)
    return _round_ratio(float(gain / Decimal(contributions)))


def absolute_gain(
    market_value: Decimal, cumulative_proventos: Decimal, contributions: Decimal
) -> Decimal:
    """Money made in absolute terms: ``V + proventos - contributions`` (2dp)."""
    return to_money(
        Decimal(market_value) + Decimal(cumulative_proventos) - Decimal(contributions)
    )


def time_weighted_return(points) -> float | None:
    """Chain daily sub-period returns, removing the day's cash flow from the numerator.

    ``r_d = (V_d - F_d) / V_{d-1} - 1`` where ``F_d`` is the net flow on day ``d``;
    ``TWR = Π(1 + r_d) - 1``. Days with no prior capital (``V_{d-1} <= 0``) contribute
    no return (the initial contribution is not a "gain"). Returns ``None`` for an
    empty series.
    """
    if not points:
        return None
    factor = Decimal("1")
    prev_v: Decimal | None = None
    for p in points:
        v = Decimal(p.market_value)
        f = Decimal(p.flow)
        if prev_v is not None and prev_v > _ZERO:
            r = (v - f) / prev_v - Decimal("1")
            factor *= Decimal("1") + r
        prev_v = v
    return _round_ratio(float(factor - Decimal("1")))


def build_cashflows(points) -> list[tuple[_date, Decimal]]:
    """Dated cash flows for XIRR from the daily points.

    Contributions leave the investor's pocket (negative), proventos and the final
    liquidation value come back (positive). Derived purely from the point stream so
    it also works when points are reconstructed from cached snapshots.
    """
    flows: list[tuple[_date, Decimal]] = []
    prev_prov = _ZERO
    for p in points:
        flow = Decimal(p.flow)
        if flow != _ZERO:
            flows.append((p.date, -flow))  # money invested = outflow
        div = Decimal(p.proventos) - prev_prov
        if div != _ZERO:
            flows.append((p.date, div))  # provento received = inflow
        prev_prov = Decimal(p.proventos)
    if points:
        last = points[-1]
        flows.append((last.date, Decimal(last.market_value)))  # final value = inflow
    return flows


def xirr(cashflows: list[tuple[_date, Decimal]], *, guess: float = 0.1) -> float | None:
    """Annualized money-weighted return of dated cash flows via Newton's method.

    Returns ``None`` when the problem is degenerate (fewer than two flows, all one
    sign) or the solver fails to converge to a residual-zero rate.
    """
    if len(cashflows) < 2:
        return None
    if len({d for d, _ in cashflows}) < 2:
        # Degenerate: all flows on a single date (e.g. the first trade viewed the same
        # day). Zero time span makes the Newton step break with the untouched guess and
        # a ~0 residual, which would fabricate a return — bail out instead.
        return None
    t0 = min(d for d, _ in cashflows)
    amounts = [((d - t0).days / 365.0, float(a)) for d, a in cashflows]
    if not (any(a > 0 for _, a in amounts) and any(a < 0 for _, a in amounts)):
        return None

    rate = guess
    for _ in range(200):
        try:
            f = sum(a / (1.0 + rate) ** t for t, a in amounts)
            df = sum(-t * a / (1.0 + rate) ** (t + 1.0) for t, a in amounts)
        except (OverflowError, ZeroDivisionError, ValueError):
            return None
        if abs(df) < 1e-12:
            break
        new_rate = rate - f / df
        if new_rate <= -0.999999:  # keep (1 + rate) strictly positive
            new_rate = (rate - 0.999999) / 2.0
        if abs(new_rate - rate) < 1e-9:
            rate = new_rate
            break
        rate = new_rate

    try:
        residual = sum(a / (1.0 + rate) ** t for t, a in amounts)
    except (OverflowError, ZeroDivisionError, ValueError):
        return None
    scale = max(1.0, sum(abs(a) for _, a in amounts))
    if abs(residual) > 1e-4 * scale:
        return None
    return _round_ratio(rate)


def compute_metrics(points) -> dict:
    """All headline metrics for a daily point series.

    ``{simple_return, twr, xirr, absolute_gain}`` — ratios as ``float`` (or ``None``),
    ``absolute_gain`` as a 2dp money ``float``.
    """
    if not points:
        return {
            "simple_return": None,
            "twr": None,
            "xirr": None,
            "absolute_gain": 0.0,
        }
    last = points[-1]
    return {
        "simple_return": simple_return(
            last.market_value, last.proventos, last.contributions
        ),
        "twr": time_weighted_return(points),
        "xirr": xirr(build_cashflows(points)),
        "absolute_gain": float(
            absolute_gain(last.market_value, last.proventos, last.contributions)
        ),
    }
