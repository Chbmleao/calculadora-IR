"""Patrimony evolution endpoint (task 05), auto-mounted under ``/api``.

``GET /api/portfolio/evolution?granularity=daily|weekly|monthly&from=&to=`` ->

    {
      "points":  [{date, market_value, contributions, proventos, invested_cost}],
      "metrics": {simple_return, twr, xirr, absolute_gain},
      "as_of":   date
    }

The daily series (first trade → ``to``/today) is reconstructed and cached in
``snapshots``; metrics are computed on the full daily resolution (TWR/XIRR need every
day), while ``from``/``to`` clip the returned points and ``granularity`` down-samples
them to period-end points. ``from`` only narrows the view; ``as_of`` / metrics always
run inception → ``to``.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.portfolio.evolution import DailyPoint, downsample, get_evolution_series
from app.portfolio.returns import compute_metrics
from app.schemas import APIModel

router = APIRouter(tags=["evolution"])


class EvolutionPointOut(APIModel):
    """One equity-curve point (money fields as 2dp numbers)."""

    date: date
    market_value: float
    contributions: float
    proventos: float
    invested_cost: float


class EvolutionMetrics(APIModel):
    """Headline return metrics for the period (ratios are fractions, e.g. 0.12 = 12%)."""

    simple_return: float | None
    twr: float | None
    xirr: float | None
    absolute_gain: float


class EvolutionResponse(APIModel):
    """Payload for ``GET /api/portfolio/evolution``."""

    points: list[EvolutionPointOut]
    metrics: EvolutionMetrics
    as_of: date


def _point_out(p: DailyPoint) -> EvolutionPointOut:
    return EvolutionPointOut(
        date=p.date,
        market_value=float(p.market_value),
        contributions=float(p.contributions),
        proventos=float(p.proventos),
        invested_cost=float(p.invested_cost),
    )


@router.get("/portfolio/evolution", response_model=EvolutionResponse)
def portfolio_evolution(
    granularity: Literal["daily", "weekly", "monthly"] = "daily",
    from_: date | None = Query(None, alias="from"),
    to: date | None = Query(None, alias="to"),
    db: Session = Depends(get_db),
) -> EvolutionResponse:
    series = get_evolution_series(db, to=to)

    metrics = compute_metrics(series.points)

    view = [p for p in series.points if from_ is None or p.date >= from_]
    view = downsample(view, granularity)

    return EvolutionResponse(
        points=[_point_out(p) for p in view],
        metrics=EvolutionMetrics(**metrics),
        as_of=series.as_of,
    )
