"""Domain helpers behind the manual-trade CRUD API (task 02b).

The ``app.api.trades`` router owns the HTTP shape and the request/response schemas;
this module owns the pure DB logic so it can be unit-tested against a real
:class:`~sqlalchemy.orm.Session` without spinning up FastAPI:

- **Sell guard net-qty** — mirrors the *"baseline + manual delta since period_end"*
  rule that :mod:`app.portfolio.positions` applies (that module is imported and
  reused elsewhere and is **never modified** here). The authoritative
  ``position_summary`` baseline holds net qty up to its latest ``period_end``; manual
  trades dated strictly after that cutoff layer on top. Ordering is irrelevant for
  *quantity* (a buy adds, a sell subtracts), so net qty is a plain sum — no avg-cost
  replay needed. When a baseline exists but carries no ``period_end`` we cannot tell
  which manual trades it already reflects, so we skip them (matching positions.py to
  avoid double counting). When there is no baseline at all, every manual trade counts.

- **Data-version bump** — dropping the cached ``snapshots`` (task 05 evolution) so the
  equity curve recomputes after a mutation. Positions are always computed live from
  the DB, so they need no invalidation.

- **Clear superseded** — removing manual trades a newer B3 import now covers
  (``trade_date <= cutoff``).

All mutating helpers leave the ``commit`` to the caller.
"""

from __future__ import annotations

from datetime import date as _date
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import PositionSummary, Snapshot, Transaction
from app.quotes.base import canonical_ticker

_ZERO = Decimal("0")


def _dec(value) -> Decimal:
    """Coerce an optional Numeric/number to a Decimal (``None`` -> 0), noise-free."""
    if value is None:
        return _ZERO
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def baseline_and_cutoff(db: Session) -> tuple[dict[str, Decimal], _date | None]:
    """Net qty per canonical ticker from ``position_summary`` + the latest ``period_end``.

    ``cutoff`` is the boundary after which manual trades are layered on top; ``None``
    when no summary row carries a ``period_end``.
    """
    baseline: dict[str, Decimal] = {}
    cutoff: _date | None = None
    for row in db.scalars(select(PositionSummary)).all():
        qty = _dec(row.qty_net)
        if qty <= _ZERO:
            continue
        ticker = canonical_ticker(row.ticker)
        if not ticker:
            continue
        baseline[ticker] = baseline.get(ticker, _ZERO) + qty
        if row.period_end is not None:
            cutoff = row.period_end if cutoff is None else max(cutoff, row.period_end)
    return baseline, cutoff


def _applicable_manual(
    db: Session,
    cutoff: _date | None,
    baseline: dict[str, Decimal],
    *,
    exclude_id: int | None = None,
) -> list[Transaction]:
    """Manual trades that layer on the baseline (post-cutoff), optionally excluding one id."""
    trades = list(
        db.scalars(select(Transaction).where(Transaction.origin == "manual")).all()
    )
    if exclude_id is not None:
        trades = [t for t in trades if t.id != exclude_id]
    if cutoff is not None:
        trades = [t for t in trades if t.trade_date is not None and t.trade_date > cutoff]
    elif baseline:
        # Baseline exists but no period boundary -> cannot tell which manual trades the
        # summary already reflects; skip (matches positions.py, avoiding double counting).
        trades = []
    return trades


def net_qty_by_ticker(
    db: Session, *, exclude_id: int | None = None
) -> dict[str, Decimal]:
    """Current net quantity per canonical ticker (baseline + post-cutoff manual deltas).

    ``exclude_id`` drops one manual trade from the tally — used when validating an edit
    so the row being changed does not count against itself.
    """
    baseline, cutoff = baseline_and_cutoff(db)
    net = dict(baseline)
    for tr in _applicable_manual(db, cutoff, baseline, exclude_id=exclude_id):
        ticker = canonical_ticker(tr.ticker)
        if not ticker:
            continue
        qty = _dec(tr.quantity)
        net[ticker] = net.get(ticker, _ZERO) + (qty if tr.side == "buy" else -qty)
    return net


def current_net_qty(
    db: Session, ticker: str, *, exclude_id: int | None = None
) -> Decimal:
    """Net quantity currently held for ``ticker`` (0 when unheld)."""
    return net_qty_by_ticker(db, exclude_id=exclude_id).get(
        canonical_ticker(ticker), _ZERO
    )


def invalidate_snapshots(db: Session) -> None:
    """Drop the evolution snapshot cache so the equity curve recomputes (task 05).

    A mutation must bump the "data version"; positions are computed live so only the
    cached ``snapshots`` need clearing. A plain delete can otherwise leave snapshots
    that still count the removed trade fresh, because the evolution freshness check
    keys on ``max(imported_at)``. The caller commits.
    """
    db.execute(delete(Snapshot))


def delete_superseded_manual(db: Session) -> int:
    """Delete manual trades dated ``<= cutoff`` (a newer B3 import now covers them).

    Returns the number of rows removed; a no-op (``0``) when there is no baseline
    cutoff. The caller commits.
    """
    _, cutoff = baseline_and_cutoff(db)
    if cutoff is None:
        return 0
    ids = [
        tr.id
        for tr in db.scalars(
            select(Transaction).where(Transaction.origin == "manual")
        ).all()
        if tr.trade_date is not None and tr.trade_date <= cutoff
    ]
    if not ids:
        return 0
    db.execute(delete(Transaction).where(Transaction.id.in_(ids)))
    return len(ids)
