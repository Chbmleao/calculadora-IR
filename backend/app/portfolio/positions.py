"""Portfolio positions & allocation builder (task 04).

``build_positions(db)`` turns the imported ``position_summary`` baseline (plus any
post-period manual trades, task 02b) into a :class:`PortfolioView`: per-ticker
quantity, average cost, invested amount, current price/value, unrealized P/L,
portfolio weight, asset class and accumulated proventos — plus portfolio totals and
an asset-class allocation breakdown.

Prices come from the task-03 quote service (cache-first, brapi -> yfinance); a
ticker whose live price cannot be resolved falls back to its last cached close, and
failing that to its invested value, and is flagged ``stale``. Money is rounded to
2dp (README §7); ``*_pct`` fields are percentages (0-100) so weights sum to ~100.
"""

from __future__ import annotations

from datetime import date as _date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import PositionSummary, Provento, Transaction
from app.portfolio.classify import display_class
from app.quotes import cache
from app.quotes.base import canonical_ticker, to_money
from app.schemas import APIModel

_ZERO = Decimal("0")
_EMPTY_MESSAGE = (
    "Nenhuma posição encontrada. Importe o resumo de negociação da B3 "
    "(Negociação - Resumo) para ver suas posições."
)


# --------------------------------------------------------------------------- #
# Schemas (defined in this feature's own module — not the shared app.schemas). #
# --------------------------------------------------------------------------- #
class Position(APIModel):
    """One held ticker's valuation row."""

    ticker: str
    asset_class: str
    quantity: float
    avg_price: float
    invested: float
    price: float | None
    price_date: _date | None
    market_value: float
    pnl: float
    pnl_pct: float
    weight_pct: float
    proventos_total: float
    stale: bool


class ClassAllocation(APIModel):
    """Aggregated market value + weight for one asset class."""

    asset_class: str
    market_value: float
    weight_pct: float


class Totals(APIModel):
    """Portfolio-wide totals."""

    invested: float
    market_value: float
    pnl: float
    pnl_pct: float
    proventos: float


class PortfolioView(APIModel):
    """Full positions + allocation payload for ``GET /api/portfolio/positions``."""

    as_of: _date | None
    totals: Totals
    positions: list[Position]
    allocation_by_class: list[ClassAllocation]
    message: str | None = None


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #
def _pct(num: Decimal, den: Decimal) -> float:
    """``num/den`` as a 2dp percentage; ``0.0`` when the denominator is zero."""
    if not den:
        return 0.0
    return round(float(num) / float(den) * 100, 2)


def _dec(value) -> Decimal:
    """Coerce an optional Numeric column to a Decimal (``None`` -> 0)."""
    return Decimal(value) if value is not None else _ZERO


def _baseline(db: Session) -> tuple[dict[str, dict], _date | None]:
    """Aggregate ``position_summary`` per canonical ticker (qty-weighted avg cost).

    Returns ``({ticker: {"qty", "avg"}}, cutoff)`` where ``cutoff`` is the latest
    ``period_end`` across the summary rows (the boundary after which manual trades
    are layered on top).
    """
    agg: dict[str, dict] = {}
    cutoff: _date | None = None
    for row in db.scalars(select(PositionSummary)).all():
        qty = _dec(row.qty_net)
        if qty <= 0:
            continue
        ticker = canonical_ticker(row.ticker)
        if not ticker:
            continue
        entry = agg.setdefault(ticker, {"qty": _ZERO, "cost": _ZERO})
        entry["qty"] += qty
        entry["cost"] += qty * _dec(row.avg_price_buy)
        if row.period_end is not None:
            cutoff = row.period_end if cutoff is None else max(cutoff, row.period_end)

    positions = {
        ticker: {"qty": e["qty"], "avg": (e["cost"] / e["qty"]) if e["qty"] else _ZERO}
        for ticker, e in agg.items()
    }
    return positions, cutoff


def _apply_manual(
    db: Session, positions: dict[str, dict], cutoff: _date | None
) -> dict[str, dict]:
    """Layer manual trades (``origin='manual'``) dated after ``cutoff`` on the baseline.

    Buy -> recompute weighted-average cost; sell -> reduce qty, keep avg. Tickers
    reaching ``qty <= 0`` are dropped. A no-op when no manual trades apply (task 02b
    not built, or none dated after the summary period).
    """
    trades = list(db.scalars(select(Transaction).where(Transaction.origin == "manual")).all())
    if cutoff is not None:
        trades = [t for t in trades if t.trade_date is not None and t.trade_date > cutoff]
    elif positions:
        # Baseline exists but no period boundary is known -> cannot safely tell which
        # manual trades are already reflected in the summary; skip to avoid double count.
        trades = []

    trades.sort(key=lambda t: (t.trade_date, t.id))
    for tr in trades:
        ticker = canonical_ticker(tr.ticker)
        if not ticker:
            continue
        entry = positions.setdefault(ticker, {"qty": _ZERO, "avg": _ZERO})
        qty = _dec(tr.quantity)
        price = _dec(tr.price)
        if tr.side == "buy":
            new_qty = entry["qty"] + qty
            if new_qty > 0:
                entry["avg"] = (entry["qty"] * entry["avg"] + qty * price) / new_qty
            entry["qty"] = new_qty
        elif tr.side == "sell":
            entry["qty"] = entry["qty"] - qty

    return {t: e for t, e in positions.items() if e["qty"] > 0}


def _proventos_by_ticker(db: Session) -> dict[str, Decimal]:
    """Sum ``net_value`` per canonical ticker across all imported proventos."""
    out: dict[str, Decimal] = {}
    for ticker, net in db.execute(select(Provento.ticker, Provento.net_value)).all():
        if not ticker:
            continue
        out[canonical_ticker(ticker)] = out.get(canonical_ticker(ticker), _ZERO) + _dec(net)
    return out


# --------------------------------------------------------------------------- #
# Public builder                                                              #
# --------------------------------------------------------------------------- #
def build_positions(db: Session, quote_service=None) -> PortfolioView:
    """Build the full :class:`PortfolioView` from persisted holdings + live quotes.

    ``quote_service`` is injectable for tests; it only needs a
    ``latest(tickers) -> {ticker: Quote}`` method. When ``None`` the real
    :class:`app.quotes.service.QuoteService` is used.
    """
    positions_raw = _apply_manual(db, *_baseline(db))
    tickers = sorted(positions_raw)

    if not tickers:
        return PortfolioView(
            as_of=None,
            totals=Totals(invested=0.0, market_value=0.0, pnl=0.0, pnl_pct=0.0, proventos=0.0),
            positions=[],
            allocation_by_class=[],
            message=_EMPTY_MESSAGE,
        )

    if quote_service is None:
        from app.quotes.service import QuoteService  # lazy: avoids heavy import in unit tests

        quote_service = QuoteService(db)
    latest = quote_service.latest(tickers)
    proventos = _proventos_by_ticker(db)

    # -- Pass 1: resolve valuation per ticker and accumulate totals. -----------
    interim: list[dict] = []
    total_invested = _ZERO
    total_market_value = _ZERO
    total_proventos = _ZERO
    as_of: _date | None = None

    for ticker in tickers:
        raw = positions_raw[ticker]
        qty = raw["qty"]
        avg = raw["avg"]
        invested = to_money(qty * avg)

        quote = latest.get(ticker)
        if quote is not None:
            price = quote.price
            price_date = quote.date
            stale = False
            market_value = to_money(qty * price)
        else:
            cached = cache.get_latest_cached(db, ticker)
            if cached is not None:
                price = cached.close
                price_date = cached.date
                stale = True
                market_value = to_money(qty * price)
            else:
                price = None
                price_date = None
                stale = True
                market_value = invested  # fallback so a missing quote never crashes

        prov = proventos.get(ticker, _ZERO)
        total_invested += invested
        total_market_value += market_value
        total_proventos += prov
        if price_date is not None:
            as_of = price_date if as_of is None else max(as_of, price_date)

        interim.append(
            {
                "ticker": ticker,
                "qty": qty,
                "avg": avg,
                "invested": invested,
                "price": price,
                "price_date": price_date,
                "market_value": market_value,
                "proventos": prov,
                "stale": stale,
            }
        )

    # -- Pass 2: weights, P/L, per-position + per-class rows. -------------------
    positions_out: list[Position] = []
    class_mv: dict[str, Decimal] = {}
    for item in interim:
        mv = item["market_value"]
        invested = item["invested"]
        cls = display_class(item["ticker"])
        class_mv[cls] = class_mv.get(cls, _ZERO) + mv
        positions_out.append(
            Position(
                ticker=item["ticker"],
                asset_class=cls,
                quantity=float(item["qty"]),
                avg_price=float(to_money(item["avg"])),
                invested=float(invested),
                price=float(to_money(item["price"])) if item["price"] is not None else None,
                price_date=item["price_date"],
                market_value=float(mv),
                pnl=float(to_money(mv - invested)),
                pnl_pct=_pct(mv - invested, invested),
                weight_pct=_pct(mv, total_market_value),
                proventos_total=float(to_money(item["proventos"])),
                stale=item["stale"],
            )
        )

    positions_out.sort(key=lambda p: p.market_value, reverse=True)

    allocation = [
        ClassAllocation(
            asset_class=cls,
            market_value=float(to_money(mv)),
            weight_pct=_pct(mv, total_market_value),
        )
        for cls, mv in class_mv.items()
    ]
    allocation.sort(key=lambda a: a.market_value, reverse=True)

    totals = Totals(
        invested=float(to_money(total_invested)),
        market_value=float(to_money(total_market_value)),
        pnl=float(to_money(total_market_value - total_invested)),
        pnl_pct=_pct(total_market_value - total_invested, total_invested),
        proventos=float(to_money(total_proventos)),
    )

    return PortfolioView(
        as_of=as_of or _date.today(),
        totals=totals,
        positions=positions_out,
        allocation_by_class=allocation,
        message=None,
    )
