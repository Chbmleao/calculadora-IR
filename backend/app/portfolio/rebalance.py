"""Target allocation & rebalancing domain (task 06).

Two related capabilities live here so the two thin routers (``app/api/targets.py``
and ``app/api/rebalance.py``) share one implementation:

* **Targets** — read / replace the desired weights stored in ``target_allocations``
  (``kind`` = ``'class'`` | ``'ticker'``). On first run the table is seeded from the
  ``.env`` ``TARGET_ALLOCATIONS`` JSON (see :func:`seed_targets_if_empty`). Each group
  (class-level, ticker-level) is expected to sum to ~100%; an off-100 sum yields a
  *warning* — it never hard-fails (README §7 / task spec).

* **Rebalancing** — :func:`build_rebalance` reuses task-04 ``build_positions`` for the
  current holdings/weights/prices and computes, per key::

      target_value = target_pct/100 * (total_market_value + contribution)
      drift_value  = target_value - current_value
      drift_pct    = current_weight - target_pct

  In **contribution mode** (``contribution > 0``, the default UI mode) new money is
  distributed to the *most underweight* assets first, **buys only** — never a sell —
  greedily filling each gap until the deposit is exhausted; whole-share quantities are
  derived from the latest price and the indivisible-share remainder is ``leftover_cash``.
  In **rebalance mode** (``contribution == 0``) the full buy(+)/sell(-) plan to hit the
  targets is returned.

**Precedence for class vs ticker targets.** A ticker with an explicit ticker-level
target uses it directly and is excluded from any class split. A class-level target is
divided among that class's held tickers *without* an explicit ticker target, weighted
by current market value (equally if they are all empty). A class with no held tickers
surfaces as a single class-level row (no share quantity, since there is nothing to size).

Money is rounded to 2dp; ``*_pct`` fields are percentages (0-100). This module never
mutates the shared positions builder — it imports ``build_positions`` read-only.
"""

from __future__ import annotations

import json
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import TargetAllocation
from app.portfolio.positions import build_positions
from app.quotes.base import canonical_ticker, to_money
from app.schemas import APIModel

_ZERO = Decimal("0")
_HUNDRED = Decimal("100")
# How far a group's target sum may drift from 100% before we warn (percentage points).
_SUM_TOLERANCE = Decimal("0.5")

# backend/app/portfolio/rebalance.py -> parents[3] = repo root (mirrors app.config).
_ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


# --------------------------------------------------------------------------- #
# Schemas (defined in this feature's own module — not the shared app.schemas). #
# --------------------------------------------------------------------------- #
class TargetItem(APIModel):
    """One stored target (class- or ticker-level)."""

    kind: str  # 'class' | 'ticker'
    key: str
    target_pct: float


class TargetsResponse(APIModel):
    """Payload for ``GET /api/targets`` — targets grouped by kind, plus warnings."""

    class_targets: list[TargetItem]
    ticker_targets: list[TargetItem]
    warnings: list[str] = Field(default_factory=list)


class TargetInput(BaseModel):
    """One target row in a ``PUT /api/targets`` body (kind implied by its list)."""

    key: str
    target_pct: float = Field(ge=0)


class TargetsUpdate(BaseModel):
    """Request body for ``PUT /api/targets`` — replaces all stored targets."""

    class_targets: list[TargetInput] = Field(default_factory=list)
    ticker_targets: list[TargetInput] = Field(default_factory=list)


class RebalanceRow(APIModel):
    """One line of the rebalancing plan (ticker-level, or class-level when empty)."""

    key: str
    kind: str  # 'ticker' | 'class'
    current_pct: float
    target_pct: float
    drift_pct: float  # current_pct - target_pct  (>0 = overweight)
    current_value: float
    target_value: float
    suggested_buy_amount: float  # +buy / -sell (rebalance mode); >=0 (contribution mode)
    suggested_buy_qty: float | None  # whole shares; None when no price is known
    price: float | None


class RebalancePlan(APIModel):
    """Payload for ``GET /api/portfolio/rebalance``."""

    mode: str  # 'contribution' | 'rebalance'
    contribution: float
    total_market_value: float
    rows: list[RebalanceRow]
    leftover_cash: float
    warnings: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Seeding source (.env TARGET_ALLOCATIONS)                                     #
# --------------------------------------------------------------------------- #
class _SeedEnv(BaseSettings):
    """Reads only ``TARGET_ALLOCATIONS`` from the same ``.env`` the app uses.

    The foundation ``Settings`` ignores unknown keys (``extra='ignore'``) and does not
    declare ``TARGET_ALLOCATIONS``, so this feature reads it here rather than editing the
    shared config module.
    """

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    TARGET_ALLOCATIONS: str = ""


def _seed_raw() -> str:
    """The raw ``TARGET_ALLOCATIONS`` JSON string (from Settings if it ever declares it)."""
    declared = getattr(get_settings(), "TARGET_ALLOCATIONS", None)
    if declared:
        return declared if isinstance(declared, str) else json.dumps(declared)
    return _SeedEnv().TARGET_ALLOCATIONS or ""


def _parse_seed(raw: str) -> dict[str, dict[str, Decimal]]:
    """Parse the seed JSON into ``{"class": {...}, "ticker": {...}}`` of Decimals.

    Tolerant: bad JSON or an unexpected shape yields ``{}`` (nothing to seed) rather
    than crashing startup.
    """
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return {}
    if not isinstance(data, dict):
        return {}

    out: dict[str, dict[str, Decimal]] = {}
    for kind in ("class", "ticker"):
        group = data.get(kind)
        if not isinstance(group, dict):
            continue
        parsed: dict[str, Decimal] = {}
        for key, pct in group.items():
            key = canonical_ticker(key) if kind == "ticker" else str(key).strip()
            if not key:
                continue
            try:
                parsed[key] = Decimal(str(pct))
            except (ValueError, TypeError):
                continue
        if parsed:
            out[kind] = parsed
    return out


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #
def _dec(value) -> Decimal:
    return Decimal(value) if value is not None else _ZERO


def _to_dec(value) -> Decimal:
    """Coerce a float/int/str to Decimal via ``str`` (avoids binary-float noise)."""
    return value if isinstance(value, Decimal) else Decimal(str(value))


def _group_sum_warnings(
    class_targets: dict[str, Decimal], ticker_targets: dict[str, Decimal]
) -> list[str]:
    """One warning per group whose targets do not sum to ~100%."""
    warnings: list[str] = []
    for label, group in (("Class", class_targets), ("Ticker", ticker_targets)):
        if not group:
            continue
        total = sum(group.values(), _ZERO)
        if abs(total - _HUNDRED) > _SUM_TOLERANCE:
            warnings.append(
                f"{label}-level targets sum to {_fmt_pct(total)}% (expected ~100%)."
            )
    return warnings


def _fmt_pct(value: Decimal) -> str:
    return f"{float(value):g}"


def _load_target_dicts(db: Session) -> tuple[dict[str, Decimal], dict[str, Decimal]]:
    """Return ``(class_targets, ticker_targets)`` keyed maps from the DB rows."""
    class_targets: dict[str, Decimal] = {}
    ticker_targets: dict[str, Decimal] = {}
    for row in db.scalars(select(TargetAllocation)).all():
        pct = _dec(row.target_pct)
        if row.kind == "class":
            class_targets[row.key] = class_targets.get(row.key, _ZERO) + pct
        else:
            key = canonical_ticker(row.key)
            ticker_targets[key] = ticker_targets.get(key, _ZERO) + pct
    return class_targets, ticker_targets


# --------------------------------------------------------------------------- #
# Targets: seed / read / replace                                              #
# --------------------------------------------------------------------------- #
def seed_targets_if_empty(db: Session) -> list[str]:
    """Seed ``target_allocations`` from the ``.env`` JSON iff the table is empty.

    Idempotent: a no-op once any target exists. Returns any group-sum warnings from the
    seeded data (empty list when nothing was seeded).
    """
    exists = db.scalar(select(TargetAllocation.id).limit(1))
    if exists is not None:
        return []

    seed = _parse_seed(_seed_raw())
    if not seed:
        return []

    class_targets = seed.get("class", {})
    ticker_targets = seed.get("ticker", {})
    for key, pct in class_targets.items():
        db.add(TargetAllocation(kind="class", key=key, target_pct=pct))
    for key, pct in ticker_targets.items():
        db.add(TargetAllocation(kind="ticker", key=key, target_pct=pct))
    db.commit()
    return _group_sum_warnings(class_targets, ticker_targets)


def load_targets(db: Session) -> TargetsResponse:
    """Read the current targets grouped by kind, with group-sum warnings."""
    class_targets, ticker_targets = _load_target_dicts(db)
    warnings = _group_sum_warnings(class_targets, ticker_targets)
    return TargetsResponse(
        class_targets=[
            TargetItem(kind="class", key=k, target_pct=float(v))
            for k, v in sorted(class_targets.items())
        ],
        ticker_targets=[
            TargetItem(kind="ticker", key=k, target_pct=float(v))
            for k, v in sorted(ticker_targets.items())
        ],
        warnings=warnings,
    )


def replace_targets(db: Session, update: TargetsUpdate) -> TargetsResponse:
    """Replace **all** stored targets with the supplied set (validated, warned).

    Duplicate keys within a group collapse to the last value (the unique
    ``(kind, key)`` constraint forbids two rows). Off-100 group sums warn but succeed.
    """
    class_targets: dict[str, Decimal] = {}
    for item in update.class_targets:
        key = str(item.key).strip()
        if key:
            class_targets[key] = _to_dec(item.target_pct)

    ticker_targets: dict[str, Decimal] = {}
    for item in update.ticker_targets:
        key = canonical_ticker(item.key)
        if key:
            ticker_targets[key] = _to_dec(item.target_pct)

    db.execute(delete(TargetAllocation))
    for key, pct in class_targets.items():
        db.add(TargetAllocation(kind="class", key=key, target_pct=pct))
    for key, pct in ticker_targets.items():
        db.add(TargetAllocation(kind="ticker", key=key, target_pct=pct))
    db.commit()

    return load_targets(db)


# --------------------------------------------------------------------------- #
# Rebalancing                                                                 #
# --------------------------------------------------------------------------- #
def _effective_targets(
    view,
    class_targets: dict[str, Decimal],
    ticker_targets: dict[str, Decimal],
) -> tuple[dict[str, dict], list[tuple[str, Decimal]]]:
    """Resolve per-ticker effective targets + leftover class rows.

    Returns ``(eff, class_rows)`` where ``eff`` maps ticker -> ``{"target_pct", "kind"}``
    and ``class_rows`` is a list of ``(class_key, target_pct)`` for classes that have no
    held tickers to split into. See the module docstring for the precedence rules.
    """
    mv_of: dict[str, Decimal] = {p.ticker: _to_dec(p.market_value) for p in view.positions}

    eff: dict[str, dict] = {}
    # 1) Explicit ticker-level targets win outright.
    for ticker, pct in ticker_targets.items():
        eff[ticker] = {"target_pct": pct, "kind": "ticker"}

    # 2) Held tickers eligible for a class split (exclude ticker-targeted ones).
    held_by_class: dict[str, list[str]] = {}
    for p in view.positions:
        if p.ticker in ticker_targets:
            continue
        held_by_class.setdefault(p.asset_class, []).append(p.ticker)

    class_rows: list[tuple[str, Decimal]] = []
    for cls, pct in class_targets.items():
        members = held_by_class.get(cls, [])
        if not members:
            class_rows.append((cls, pct))
            continue
        total_cls_mv = sum((mv_of[t] for t in members), _ZERO)
        for t in members:
            if total_cls_mv > 0:
                share = pct * mv_of[t] / total_cls_mv
            else:  # all members empty -> split equally
                share = pct / Decimal(len(members))
            entry = eff.setdefault(t, {"target_pct": _ZERO, "kind": "class"})
            entry["target_pct"] += share
    return eff, class_rows


def build_rebalance(db: Session, contribution=0, quote_service=None) -> RebalancePlan:
    """Compute the rebalancing plan for the current portfolio.

    ``contribution`` (>= 0) selects the mode: ``> 0`` distributes a deposit via buys
    only, most-underweight first; ``0`` returns the full buy/sell rebalance. Targets are
    read as-is from the DB (call :func:`seed_targets_if_empty` first at the API edge for
    first-run seeding). ``quote_service`` is forwarded to ``build_positions`` for tests.
    """
    contribution = _to_dec(contribution)
    if contribution < 0:
        raise ValueError("contribution must be >= 0")

    view = build_positions(db, quote_service=quote_service)
    total_mv = _to_dec(view.totals.market_value)
    base = total_mv + contribution

    price_of: dict[str, Decimal | None] = {
        p.ticker: (_to_dec(p.price) if p.price is not None else None) for p in view.positions
    }
    weight_of: dict[str, float] = {p.ticker: p.weight_pct for p in view.positions}
    mv_of: dict[str, Decimal] = {p.ticker: _to_dec(p.market_value) for p in view.positions}

    class_targets, ticker_targets = _load_target_dicts(db)
    warnings = _group_sum_warnings(class_targets, ticker_targets)
    eff, class_rows = _effective_targets(view, class_targets, ticker_targets)

    # -- Assemble raw rows (ticker-level for the union of held + targeted tickers). ----
    rows: list[dict] = []
    for ticker in sorted(set(mv_of) | set(eff)):
        target_pct = eff.get(ticker, {}).get("target_pct", _ZERO)
        kind = eff.get(ticker, {}).get("kind", "ticker")
        current_value = mv_of.get(ticker, _ZERO)
        current_pct = weight_of.get(ticker, 0.0)
        target_value = base * target_pct / _HUNDRED
        rows.append(
            {
                "key": ticker,
                "kind": kind,
                "current_pct": current_pct,
                "target_pct": target_pct,
                "current_value": current_value,
                "target_value": target_value,
                "drift_value": target_value - current_value,
                "price": price_of.get(ticker),
                "alloc": _ZERO,
            }
        )
    # Class-level rows for classes with no holdings to size against.
    for cls, pct in class_rows:
        target_value = base * pct / _HUNDRED
        rows.append(
            {
                "key": cls,
                "kind": "class",
                "current_pct": 0.0,
                "target_pct": pct,
                "current_value": _ZERO,
                "target_value": target_value,
                "drift_value": target_value,
                "price": None,
                "alloc": _ZERO,
            }
        )

    mode = "contribution" if contribution > 0 else "rebalance"
    if mode == "contribution":
        leftover = _allocate_contribution(rows, contribution)
    else:
        leftover = _ZERO
        for row in rows:
            row["alloc"] = row["drift_value"]  # full plan: buy(+)/sell(-) to target

    # -- Materialize output rows. ----------------------------------------------------
    out_rows = [_finalize_row(row, mode) for row in rows]
    # Contribution mode: leftover is deposit minus what whole shares actually consume.
    if mode == "contribution":
        spent = sum((_to_dec(r.suggested_buy_amount) for r in out_rows), _ZERO)
        leftover = contribution - spent

    # Show the biggest actions first.
    out_rows.sort(key=lambda r: (-r.suggested_buy_amount, -r.current_value, r.key))

    return RebalancePlan(
        mode=mode,
        contribution=float(to_money(contribution)),
        total_market_value=float(to_money(total_mv)),
        rows=out_rows,
        leftover_cash=float(to_money(leftover)),
        warnings=warnings,
    )


def _allocate_contribution(rows: list[dict], contribution: Decimal) -> Decimal:
    """Greedily assign the deposit to underweight rows, most-underweight first.

    Fills each row's ``drift_value`` gap (buys only) until the deposit is exhausted.
    Writes the continuous amount into ``row["alloc"]`` and returns the unassigned
    remainder (before whole-share rounding).
    """
    candidates = sorted(
        (r for r in rows if r["drift_value"] > 0),
        key=lambda r: r["drift_value"],
        reverse=True,
    )
    remaining = contribution
    for row in candidates:
        if remaining <= 0:
            break
        buy = min(remaining, row["drift_value"])
        row["alloc"] = buy
        remaining -= buy
    return remaining


def _finalize_row(row: dict, mode: str) -> RebalanceRow:
    """Turn a raw row dict into a :class:`RebalanceRow` (whole-share sizing + rounding)."""
    price = row["price"]
    if mode == "contribution":
        alloc = row["alloc"]
        if price is not None and price > 0:
            qty = int(alloc // price)  # floor: never overshoot the deposit
            buy_amount = to_money(qty * price)
            buy_qty: float | None = float(qty)
        else:
            buy_amount = to_money(alloc)
            buy_qty = None
    else:  # rebalance: exact drift as the amount, nearest whole share as the qty
        amount = row["alloc"]
        buy_amount = to_money(amount)
        if price is not None and price > 0:
            buy_qty = float((amount / price).to_integral_value(rounding=ROUND_HALF_UP))
        else:
            buy_qty = None

    return RebalanceRow(
        key=row["key"],
        kind=row["kind"],
        current_pct=round(row["current_pct"], 2),
        target_pct=round(float(row["target_pct"]), 2),
        drift_pct=round(row["current_pct"] - float(row["target_pct"]), 2),
        current_value=float(to_money(row["current_value"])),
        target_value=float(to_money(row["target_value"])),
        suggested_buy_amount=float(buy_amount),
        suggested_buy_qty=buy_qty,
        price=float(to_money(price)) if price is not None else None,
    )
