import { useMemo, useState } from "react";
import clsx from "clsx";

import type { Position } from "../api/types";
import { formatBRL, formatDate, formatPct } from "../lib/format";

interface DashboardPositionsTableProps {
  positions: Position[];
}

type SortKey = "ticker" | "market_value" | "pnl" | "weight_pct";
type SortDir = "asc" | "desc";

const qtyFmt = new Intl.NumberFormat("pt-BR", {
  minimumFractionDigits: 0,
  maximumFractionDigits: 8,
});

/** Right-aligned, sortable numeric columns + the ticker. */
const SORTABLE: Record<SortKey, SortDir> = {
  ticker: "asc",
  market_value: "desc",
  pnl: "desc",
  weight_pct: "desc",
};

function SortHeader({
  label,
  columnKey,
  active,
  dir,
  align = "right",
  onSort,
}: {
  label: string;
  columnKey: SortKey;
  active: boolean;
  dir: SortDir;
  align?: "left" | "right";
  onSort: (key: SortKey) => void;
}) {
  return (
    <th
      scope="col"
      aria-sort={active ? (dir === "asc" ? "ascending" : "descending") : "none"}
      className={clsx(
        "whitespace-nowrap px-3 py-2 font-medium",
        align === "right" ? "text-right" : "text-left",
      )}
    >
      <button
        type="button"
        onClick={() => onSort(columnKey)}
        className={clsx(
          "inline-flex items-center gap-1 transition-colors hover:text-neutral-900 dark:hover:text-neutral-100",
          align === "right" && "flex-row-reverse",
          active
            ? "text-neutral-900 dark:text-neutral-100"
            : "text-neutral-500 dark:text-neutral-400",
        )}
      >
        {label}
        <span aria-hidden className="text-[10px] leading-none">
          {active ? (dir === "asc" ? "▲" : "▼") : "↕"}
        </span>
      </button>
    </th>
  );
}

/**
 * Sortable holdings table (task 09). Columns: ticker, class, qty, avg price,
 * invested, price (+ date / stale badge), market value, P/L (R$ + %) and a
 * weight column with an inline bar. Stale rows are visually flagged.
 */
export function DashboardPositionsTable({
  positions,
}: DashboardPositionsTableProps) {
  const [sortKey, setSortKey] = useState<SortKey>("weight_pct");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  const handleSort = (key: SortKey) => {
    if (key === sortKey) {
      setSortDir((prev) => (prev === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir(SORTABLE[key]);
    }
  };

  const maxWeight = useMemo(
    () => positions.reduce((max, p) => Math.max(max, p.weight_pct), 0),
    [positions],
  );

  const sorted = useMemo(() => {
    const rows = [...positions];
    rows.sort((a, b) => {
      let cmp: number;
      if (sortKey === "ticker") {
        cmp = a.ticker.localeCompare(b.ticker, "pt-BR");
      } else {
        cmp = a[sortKey] - b[sortKey];
      }
      return sortDir === "asc" ? cmp : -cmp;
    });
    return rows;
  }, [positions, sortKey, sortDir]);

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[56rem] border-collapse text-sm">
        <thead>
          <tr className="border-b border-neutral-200 text-xs dark:border-neutral-800">
            <SortHeader
              label="Ticker"
              columnKey="ticker"
              align="left"
              active={sortKey === "ticker"}
              dir={sortDir}
              onSort={handleSort}
            />
            <th scope="col" className="whitespace-nowrap px-3 py-2 text-left font-medium text-neutral-500 dark:text-neutral-400">
              Class
            </th>
            <th scope="col" className="whitespace-nowrap px-3 py-2 text-right font-medium text-neutral-500 dark:text-neutral-400">
              Qty
            </th>
            <th scope="col" className="whitespace-nowrap px-3 py-2 text-right font-medium text-neutral-500 dark:text-neutral-400">
              Avg price
            </th>
            <th scope="col" className="whitespace-nowrap px-3 py-2 text-right font-medium text-neutral-500 dark:text-neutral-400">
              Invested
            </th>
            <th scope="col" className="whitespace-nowrap px-3 py-2 text-right font-medium text-neutral-500 dark:text-neutral-400">
              Price
            </th>
            <SortHeader
              label="Market value"
              columnKey="market_value"
              active={sortKey === "market_value"}
              dir={sortDir}
              onSort={handleSort}
            />
            <SortHeader
              label="P/L"
              columnKey="pnl"
              active={sortKey === "pnl"}
              dir={sortDir}
              onSort={handleSort}
            />
            <SortHeader
              label="Weight"
              columnKey="weight_pct"
              active={sortKey === "weight_pct"}
              dir={sortDir}
              onSort={handleSort}
            />
          </tr>
        </thead>
        <tbody className="divide-y divide-neutral-100 dark:divide-neutral-800/70">
          {sorted.map((position) => {
            const gain = position.pnl >= 0;
            const barPct =
              maxWeight > 0 ? (position.weight_pct / maxWeight) * 100 : 0;
            return (
              <tr
                key={position.ticker}
                className={clsx(
                  "transition-colors",
                  position.stale
                    ? "bg-amber-50/70 hover:bg-amber-100/70 dark:bg-amber-950/30 dark:hover:bg-amber-950/50"
                    : "hover:bg-neutral-50 dark:hover:bg-neutral-800/40",
                )}
              >
                <td className="whitespace-nowrap px-3 py-2 font-semibold text-neutral-900 dark:text-neutral-50">
                  {position.ticker}
                </td>
                <td className="whitespace-nowrap px-3 py-2 text-neutral-600 dark:text-neutral-300">
                  <span className="inline-flex items-center rounded-full bg-neutral-100 px-2 py-0.5 text-xs font-medium dark:bg-neutral-800">
                    {position.asset_class}
                  </span>
                </td>
                <td className="whitespace-nowrap px-3 py-2 text-right tabular-nums text-neutral-700 dark:text-neutral-200">
                  {qtyFmt.format(position.quantity)}
                </td>
                <td className="whitespace-nowrap px-3 py-2 text-right tabular-nums text-neutral-700 dark:text-neutral-200">
                  {formatBRL(position.avg_price)}
                </td>
                <td className="whitespace-nowrap px-3 py-2 text-right tabular-nums text-neutral-700 dark:text-neutral-200">
                  {formatBRL(position.invested)}
                </td>
                <td className="whitespace-nowrap px-3 py-2 text-right tabular-nums text-neutral-700 dark:text-neutral-200">
                  <div className="flex flex-col items-end">
                    <span>{formatBRL(position.price)}</span>
                    {position.stale ? (
                      <span className="mt-0.5 inline-flex items-center gap-1 rounded-full bg-amber-100 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-amber-800 dark:bg-amber-900/60 dark:text-amber-200">
                        <span aria-hidden>⚠</span> Stale
                      </span>
                    ) : (
                      position.price_date != null && (
                        <span className="mt-0.5 text-[10px] text-neutral-400 dark:text-neutral-500">
                          {formatDate(position.price_date)}
                        </span>
                      )
                    )}
                  </div>
                </td>
                <td className="whitespace-nowrap px-3 py-2 text-right tabular-nums font-medium text-neutral-900 dark:text-neutral-50">
                  {formatBRL(position.market_value)}
                </td>
                <td className="whitespace-nowrap px-3 py-2 text-right tabular-nums">
                  <div
                    className={clsx(
                      "flex flex-col items-end",
                      gain
                        ? "text-emerald-600 dark:text-emerald-400"
                        : "text-rose-600 dark:text-rose-400",
                    )}
                  >
                    <span className="font-medium">{formatBRL(position.pnl)}</span>
                    <span className="text-xs">
                      {formatPct(position.pnl_pct, { signed: true })}
                    </span>
                  </div>
                </td>
                <td className="whitespace-nowrap px-3 py-2 text-right tabular-nums">
                  <div className="flex items-center justify-end gap-2">
                    <span className="hidden h-1.5 w-16 overflow-hidden rounded-full bg-neutral-200 dark:bg-neutral-700 sm:block">
                      <span
                        className="block h-full rounded-full bg-brand-500"
                        style={{ width: `${barPct}%` }}
                      />
                    </span>
                    <span className="w-14 font-medium text-neutral-900 dark:text-neutral-50">
                      {formatPct(position.weight_pct)}
                    </span>
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
