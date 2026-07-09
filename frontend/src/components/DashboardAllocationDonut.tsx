import { useEffect, useMemo, useState } from "react";
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";

import type { ClassAllocation } from "../api/types";
import { formatBRL, formatPct } from "../lib/format";

interface DashboardAllocationDonutProps {
  allocation: ClassAllocation[];
  /** Sum of market value across classes — rendered in the donut hole. */
  totalValue: number;
}

/**
 * Colorblind-safe categorical palette from the `dataviz` reference palette,
 * as `[light, dark]` hex pairs. Known B3 asset classes get a stable hue; any
 * unexpected class falls back to the remaining slots in order.
 */
const KNOWN_COLORS: Record<string, readonly [string, string]> = {
  Ação: ["#2a78d6", "#3987e5"], // blue
  FII: ["#1baf7a", "#199e70"], // aqua
  ETF: ["#eda100", "#c98500"], // yellow
  BDR: ["#4a3aa7", "#9085e9"], // violet
};

const FALLBACK_COLORS: readonly (readonly [string, string])[] = [
  ["#e34948", "#e66767"], // red
  ["#e87ba4", "#d55181"], // magenta
  ["#eb6834", "#d95926"], // orange
  ["#008300", "#008300"], // green
];

/** Tracks the OS/browser `prefers-color-scheme` so SVG hex can follow the theme. */
function usePrefersDark(): boolean {
  const [dark, setDark] = useState(
    () =>
      typeof window !== "undefined" &&
      typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-color-scheme: dark)").matches,
  );

  useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
      return;
    }
    const query = window.matchMedia("(prefers-color-scheme: dark)");
    const handler = (event: MediaQueryListEvent) => setDark(event.matches);
    query.addEventListener("change", handler);
    return () => query.removeEventListener("change", handler);
  }, []);

  return dark;
}

interface Slice {
  name: string;
  value: number;
  weight_pct: number;
  color: string;
}

interface SliceLabelProps {
  cx: number;
  cy: number;
  midAngle: number;
  innerRadius: number;
  outerRadius: number;
  weight_pct: number;
}

const RADIAN = Math.PI / 180;

/** Draws the weight % inside slices wide enough to hold legible text. */
function renderSliceLabel(props: SliceLabelProps) {
  const { cx, cy, midAngle, innerRadius, outerRadius, weight_pct } = props;
  if (weight_pct < 7) return null;
  const radius = innerRadius + (outerRadius - innerRadius) * 0.5;
  const x = cx + radius * Math.cos(-midAngle * RADIAN);
  const y = cy + radius * Math.sin(-midAngle * RADIAN);
  return (
    <text
      x={x}
      y={y}
      fill="#ffffff"
      textAnchor="middle"
      dominantBaseline="central"
      fontSize={12}
      fontWeight={600}
    >
      {`${Math.round(weight_pct)}%`}
    </text>
  );
}

interface TooltipEntry {
  payload: Slice;
}

function DonutTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: TooltipEntry[];
}) {
  if (!active || !payload || payload.length === 0) return null;
  const slice = payload[0].payload;
  return (
    <div className="rounded-lg border border-neutral-200 bg-white px-3 py-2 text-xs shadow-md dark:border-neutral-700 dark:bg-neutral-900">
      <div className="flex items-center gap-2 font-semibold text-neutral-800 dark:text-neutral-100">
        <span
          aria-hidden
          className="inline-block h-2.5 w-2.5 rounded-sm"
          style={{ backgroundColor: slice.color }}
        />
        {slice.name}
      </div>
      <div className="mt-1 tabular-nums text-neutral-600 dark:text-neutral-300">
        {formatBRL(slice.value)}
      </div>
      <div className="tabular-nums text-neutral-500 dark:text-neutral-400">
        {formatPct(slice.weight_pct)}
      </div>
    </div>
  );
}

/**
 * Allocation-by-asset-class donut (task 09). Slices are labeled with the weight
 * %, a side legend lists each class value + weight, and the donut hole shows the
 * portfolio total. Colors are theme-aware and colorblind-safe.
 */
export function DashboardAllocationDonut({
  allocation,
  totalValue,
}: DashboardAllocationDonutProps) {
  const dark = usePrefersDark();

  const slices = useMemo<Slice[]>(() => {
    let fallbackIndex = 0;
    return allocation.map((item) => {
      const known = KNOWN_COLORS[item.asset_class];
      const pair = known ?? FALLBACK_COLORS[fallbackIndex++ % FALLBACK_COLORS.length];
      return {
        name: item.asset_class,
        value: item.market_value,
        weight_pct: item.weight_pct,
        color: dark ? pair[1] : pair[0],
      };
    });
  }, [allocation, dark]);

  return (
    <div className="flex flex-col gap-4 lg:flex-row lg:items-center">
      <div className="relative mx-auto aspect-square w-full max-w-[16rem] shrink-0">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={slices}
              dataKey="value"
              nameKey="name"
              cx="50%"
              cy="50%"
              innerRadius="60%"
              outerRadius="88%"
              paddingAngle={1}
              stroke="none"
              isAnimationActive={false}
              label={renderSliceLabel}
              labelLine={false}
            >
              {slices.map((slice) => (
                <Cell key={slice.name} fill={slice.color} />
              ))}
            </Pie>
            <Tooltip content={<DonutTooltip />} />
          </PieChart>
        </ResponsiveContainer>
        {/* Donut hole: portfolio total. */}
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-[10px] font-medium uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
            Total
          </span>
          <span className="max-w-[70%] truncate text-center text-sm font-semibold tabular-nums text-neutral-900 dark:text-neutral-50">
            {formatBRL(totalValue)}
          </span>
        </div>
      </div>

      {/* Legend: one row per class with its value + weight. */}
      <ul className="flex flex-1 flex-col gap-2" aria-label="Allocation by asset class">
        {slices.map((slice) => (
          <li
            key={slice.name}
            className="flex items-center justify-between gap-3 text-sm"
          >
            <span className="flex min-w-0 items-center gap-2">
              <span
                aria-hidden
                className="inline-block h-3 w-3 shrink-0 rounded-sm"
                style={{ backgroundColor: slice.color }}
              />
              <span className="truncate font-medium text-neutral-700 dark:text-neutral-200">
                {slice.name}
              </span>
            </span>
            <span className="flex shrink-0 items-center gap-2 tabular-nums">
              <span className="text-neutral-600 dark:text-neutral-300">
                {formatBRL(slice.value)}
              </span>
              <span className="w-14 text-right font-semibold text-neutral-900 dark:text-neutral-50">
                {formatPct(slice.weight_pct)}
              </span>
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
