"""Quote endpoints (task 03), auto-mounted under ``/api``.

- ``GET  /api/quotes/latest``  -> ``{ticker: {price, date, source}}`` for held tickers.
- ``POST /api/quotes/refresh`` -> force a refresh and report how many were updated.

History is consumed internally by the evolution layer (task 05); no public route.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.quotes.base import Quote
from app.quotes.service import QuoteService, get_portfolio_tickers
from app.schemas import APIModel

router = APIRouter(tags=["quotes"])


class LatestQuote(APIModel):
    """One ticker's latest price payload."""

    price: float
    date: date
    source: str


class RefreshResult(APIModel):
    """Result of a forced refresh."""

    updated: int


def _to_payload(quotes: dict[str, Quote]) -> dict[str, LatestQuote]:
    return {
        ticker: LatestQuote(price=float(q.price), date=q.date, source=q.source)
        for ticker, q in quotes.items()
    }


@router.get("/quotes/latest", response_model=dict[str, LatestQuote])
def latest_quotes(db: Session = Depends(get_db)) -> dict[str, LatestQuote]:
    tickers = get_portfolio_tickers(db)
    quotes = QuoteService(db).latest(tickers)
    return _to_payload(quotes)


@router.post("/quotes/refresh", response_model=RefreshResult)
def refresh_quotes(db: Session = Depends(get_db)) -> RefreshResult:
    tickers = get_portfolio_tickers(db)
    quotes = QuoteService(db).refresh_latest(tickers)
    return RefreshResult(updated=len(quotes))
