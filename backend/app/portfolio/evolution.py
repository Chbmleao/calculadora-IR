"""Patrimony evolution — full historical reconstruction (task 05).

We rebuild the portfolio's daily market value from first trade to today by:

1. **Holdings timeline** — walk ``transactions`` in date order, keeping a running
   quantity and average-cost basis per ticker (``buy`` adds, ``sell`` removes at
   average cost).
2. **Historical prices** — pull daily closes per held ticker via the task-03 quote
   service (cache-first / delta-fetched) and **forward-fill** weekends, holidays and
   gaps with the last known close.
3. **Daily valuation** — for every calendar day: ``market_value`` = Σ qty·price,
   cumulative net ``contributions`` (Σ buy value − Σ sell value), cumulative
   ``proventos`` (net_value with ``pay_date ≤ d``) and ``invested_cost`` (Σ per-ticker
   average-cost basis of shares still held).

**Unpriced holdings:** a ticker held before its quote history begins has no close on
those days. Per the spec's "treat as cost" option we value it at its average-cost
basis (so the curve stays continuous instead of dropping to zero) and surface the
ticker in ``unpriced_tickers`` so the caller can flag it.

**Caching:** each daily point is persisted to ``snapshots`` (task 01). A repeat
request whose snapshots are *fresh* (all ``computed_at`` ≥ the latest import time)
and cover the requested end date is served entirely from the cache with **no** quote
lookups. A new import bumps the import timestamp past the snapshots' ``computed_at``,
which invalidates the cache and forces a full recompute (the single-user MVP replaces
the whole snapshot table rather than splicing incremental tails).
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import date as _date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import Provento, Snapshot, Transaction
from app.quotes.base import canonical_ticker, to_money
from app.quotes.service import QuoteService

logger = logging.getLogger(__name__)

_ZERO = Decimal("0")
_ONE_DAY = timedelta(days=1)


def _dec(value) -> Decimal:
    """Coerce to Decimal without binary-float noise; ``None`` -> 0."""
    if value is None:
        return _ZERO
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _now_utc_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _as_naive_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


@dataclass(frozen=True)
class DailyPoint:
    """One day of the equity curve.

    ``flow`` is the *net* cash flow on this day (buy value − sell value); it is
    internal (used by TWR/XIRR) and not part of the API payload.
    """

    date: _date
    market_value: Decimal
    contributions: Decimal
    proventos: Decimal
    invested_cost: Decimal
    flow: Decimal


@dataclass
class EvolutionSeries:
    """Full daily series plus provenance for the API layer."""

    points: list[DailyPoint]
    as_of: _date
    unpriced_tickers: list[str]
    from_cache: bool


# --------------------------------------------------------------------------- #
# Holdings reconstruction                                                      #
# --------------------------------------------------------------------------- #


def holdings_as_of(transactions, on_date: _date) -> dict[str, Decimal]:
    """Net quantity held per ticker as of ``on_date`` (inclusive of that day's trades).

    Pure helper over anything exposing ``trade_date``/``ticker``/``side``/``quantity``
    (ORM rows or lightweight stand-ins), so holdings reconstruction is testable in
    isolation. Tickers netting to zero are dropped.
    """
    holdings: dict[str, Decimal] = defaultdict(lambda: _ZERO)
    for t in sorted(transactions, key=lambda x: x.trade_date):
        if t.trade_date > on_date:
            break
        qty = _dec(t.quantity)
        holdings[t.ticker] += -qty if t.side == "sell" else qty
    return {tk: q for tk, q in holdings.items() if q != _ZERO}


# --------------------------------------------------------------------------- #
# Pure daily valuation                                                         #
# --------------------------------------------------------------------------- #


def compute_daily_series(
    transactions,
    proventos,
    prices: dict[str, dict[_date, Decimal]],
    start: _date,
    end: _date,
) -> tuple[list[DailyPoint], list[str]]:
    """Build the daily equity curve over ``[start, end]`` — pure, no DB/network.

    ``prices`` maps ticker -> {date: close} (sparse daily closes, as returned by the
    quote service); missing days are forward-filled from the last known close. Ticker
    keys must match the transaction tickers (canonical). Returns
    ``(points, unpriced_tickers)``.
    """
    txns_by_day: dict[_date, list] = defaultdict(list)
    for t in transactions:
        txns_by_day[t.trade_date].append(t)

    prov_by_day: dict[_date, Decimal] = defaultdict(lambda: _ZERO)
    for p in proventos:
        if p.pay_date is not None and p.net_value is not None:
            prov_by_day[p.pay_date] += _dec(p.net_value)

    holdings: dict[str, Decimal] = defaultdict(lambda: _ZERO)
    cost_basis: dict[str, Decimal] = defaultdict(lambda: _ZERO)
    last_close: dict[str, Decimal] = {}
    contributions = _ZERO
    cum_proventos = _ZERO

    points: list[DailyPoint] = []
    unpriced: set[str] = set()

    day = start
    while day <= end:
        day_flow = _ZERO
        for t in txns_by_day.get(day, ()):
            qty = _dec(t.quantity)
            val = _dec(t.value)
            ticker = t.ticker
            if t.side == "sell":
                held = holdings[ticker]
                avg = (cost_basis[ticker] / held) if held > _ZERO else _ZERO
                sold = min(qty, held) if held > _ZERO else _ZERO
                holdings[ticker] = held - qty
                cost_basis[ticker] = max(_ZERO, cost_basis[ticker] - avg * sold)
                contributions -= val
                day_flow -= val
            else:  # buy
                holdings[ticker] += qty
                cost_basis[ticker] += val
                contributions += val
                day_flow += val

        for ticker, series in prices.items():
            close = series.get(day)
            if close is not None:
                last_close[ticker] = _dec(close)

        cum_proventos += prov_by_day.get(day, _ZERO)

        market_value = _ZERO
        invested_cost = _ZERO
        for ticker, qty in holdings.items():
            if qty <= _ZERO:
                continue
            basis = cost_basis[ticker]
            invested_cost += basis
            close = last_close.get(ticker)
            if close is None:
                unpriced.add(ticker)
                market_value += basis  # value unpriced holdings at cost
            else:
                market_value += qty * close

        points.append(
            DailyPoint(
                date=day,
                market_value=to_money(market_value),
                contributions=to_money(contributions),
                proventos=to_money(cum_proventos),
                invested_cost=to_money(invested_cost),
                flow=to_money(day_flow),
            )
        )
        day += _ONE_DAY

    return points, sorted(unpriced)


def forward_filled_prices(rows, start: _date, end: _date) -> dict[_date, Decimal]:
    """Dense {date: close} over ``[start, end]`` forward-filled from sparse closes.

    ``rows`` is an iterable of objects with ``date``/``close`` (e.g. ``DailyClose``).
    Days before the first known close are omitted (no price yet).
    """
    by_day = {r.date: _dec(r.close) for r in rows}
    dense: dict[_date, Decimal] = {}
    last: Decimal | None = None
    day = start
    while day <= end:
        if day in by_day:
            last = by_day[day]
        if last is not None:
            dense[day] = last
        day += _ONE_DAY
    return dense


# --------------------------------------------------------------------------- #
# Orchestration + snapshot cache                                              #
# --------------------------------------------------------------------------- #


def _load_transactions(db: Session) -> list[Transaction]:
    return list(
        db.scalars(select(Transaction).order_by(Transaction.trade_date)).all()
    )


def _load_proventos(db: Session) -> list[Provento]:
    return list(db.scalars(select(Provento)).all())


def _data_version(db: Session) -> datetime | None:
    """Latest ingest timestamp across transactions + proventos (naive UTC)."""
    t = db.execute(select(func.max(Transaction.imported_at))).scalar_one()
    p = db.execute(select(func.max(Provento.imported_at))).scalar_one()
    stamps = [_as_naive_utc(x) for x in (t, p) if x is not None]
    return max(stamps) if stamps else None


def _load_snapshots(db: Session) -> list[Snapshot]:
    return list(db.scalars(select(Snapshot).order_by(Snapshot.date)).all())


def _snapshots_fresh(snapshots: list[Snapshot], data_version: datetime | None) -> bool:
    """True when every snapshot was computed at/after the last import."""
    if not snapshots:
        return False
    if data_version is None:
        return True
    return all(
        (_as_naive_utc(s.computed_at) or datetime.min) >= data_version
        for s in snapshots
    )


def _points_from_snapshots(snapshots: list[Snapshot], end: _date) -> list[DailyPoint]:
    """Rebuild daily points (incl. derived ``flow``) from cached snapshot rows."""
    rows = sorted((s for s in snapshots if s.date <= end), key=lambda s: s.date)
    points: list[DailyPoint] = []
    prev_contrib = _ZERO
    for s in rows:
        contrib = _dec(s.contributions_to_date)
        points.append(
            DailyPoint(
                date=s.date,
                market_value=_dec(s.total_value),
                contributions=contrib,
                proventos=_dec(s.cumulative_proventos),
                invested_cost=_dec(s.total_cost),
                flow=contrib - prev_contrib,
            )
        )
        prev_contrib = contrib
    return points


def _persist_snapshots(db: Session, points: list[DailyPoint]) -> None:
    """Replace the snapshot table with the freshly computed daily points."""
    now = _now_utc_naive()
    db.execute(delete(Snapshot))
    db.add_all(
        [
            Snapshot(
                date=p.date,
                total_value=p.market_value,
                total_cost=p.invested_cost,
                contributions_to_date=p.contributions,
                cumulative_proventos=p.proventos,
                computed_at=now,
            )
            for p in points
        ]
    )
    db.commit()


def _recompute(
    db: Session,
    transactions: list[Transaction],
    proventos: list[Provento],
    start: _date,
    end: _date,
    quote_service,
) -> tuple[list[DailyPoint], list[str]]:
    service = quote_service or QuoteService(db)
    tickers = sorted({canonical_ticker(t.ticker) for t in transactions})
    prices: dict[str, dict[_date, Decimal]] = {}
    for ticker in tickers:
        history = service.history(ticker, start, end)
        prices[ticker] = forward_filled_prices(history, start, end)
    return compute_daily_series(transactions, proventos, prices, start, end)


def get_evolution_series(
    db: Session,
    *,
    quote_service=None,
    to: _date | None = None,
) -> EvolutionSeries:
    """Daily equity curve from first trade to ``to`` (default today), cache-first.

    ``quote_service`` is injectable (real :class:`QuoteService` by default) so unit
    tests can supply deterministic prices without touching the network.
    """
    transactions = _load_transactions(db)
    today = _date.today()
    end = to or today
    if end > today:
        end = today

    if not transactions:
        return EvolutionSeries([], end, [], from_cache=False)

    first = min(t.trade_date for t in transactions)
    if end < first:
        return EvolutionSeries([], end, [], from_cache=False)

    data_version = _data_version(db)
    snapshots = _load_snapshots(db)
    if _snapshots_fresh(snapshots, data_version):
        last_cached = max(s.date for s in snapshots)
        if last_cached >= end:
            return EvolutionSeries(
                _points_from_snapshots(snapshots, end), end, [], from_cache=True
            )

    proventos = _load_proventos(db)
    points, unpriced = _recompute(
        db, transactions, proventos, first, end, quote_service
    )
    _persist_snapshots(db, points)
    return EvolutionSeries(points, end, unpriced, from_cache=False)


# --------------------------------------------------------------------------- #
# Granularity down-sampling                                                    #
# --------------------------------------------------------------------------- #


def downsample(points: list[DailyPoint], granularity: str) -> list[DailyPoint]:
    """Reduce a daily series to period-end points (weekly/monthly); daily = identity."""
    if granularity == "daily" or not points:
        return list(points)
    if granularity == "weekly":
        def key(d: _date):
            iso = d.isocalendar()
            return (iso[0], iso[1])
    elif granularity == "monthly":
        def key(d: _date):
            return (d.year, d.month)
    else:
        return list(points)

    out: list[DailyPoint] = []
    for i, p in enumerate(points):
        is_last = i == len(points) - 1
        if is_last or key(points[i + 1].date) != key(p.date):
            out.append(p)
    return out
