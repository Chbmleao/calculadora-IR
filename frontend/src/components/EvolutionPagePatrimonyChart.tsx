import { useEffect, useMemo, useState } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import clsx from "clsx";

import type { EvolutionGranularity, EvolutionPointOut } from "../api/types";
import { formatBRL, formatDate } from "../lib/format";

/** Period presets that scope the equity curve (client-side, relative to `as_of`). */
export type Period = "ytd" | "1y" | "all";

interface EvolutionPagePatrimonyChartProps {
  points: EvolutionPointOut[];
  granularity: EvolutionGranularity;
  period: Period;
  /** ISO date the curve is current to — anchors the period presets. */
  asOf: string;
}

/**
 * Colorblind-safe roles from the `dataviz` reference palette, as concrete hex
 * per theme. Blue↔orange is the maximally CVD-separated pair (patrimony vs.
 * contributions); the gain band and proventos take distinct further hues.
 */
interface ChartPalette {
  patrimony: string;
  contributions: string;
  gainPos: string;
  gainNeg: string;
  proventos: string;
  grid: string;
  axis: string;
  surface: string;
  cursor: string;
}

const LIGHT: ChartPalette = {
  patrimony: "#2a78d6", // blue
  contributions: "#eb6834", // orange
  gainPos: "#1baf7a", // aqua
  gainNeg: "#e34948", // red
  proventos: "#4a3aa7", // violet
  grid: "#e1e0d9",
  axis: "#898781",
  surface: "#ffffff",
  cursor: "#c3c2b7",
};

const DARK: ChartPalette = {
  patrimony: "#3987e5",
  contributions: "#d95926",
  gainPos: "#199e70",
  gainNeg: "#e66767",
  proventos: "#9085e9",
  grid: "#2c2c2a",
  axis: "#898781",
  surface: "#171717", // matches Card dark surface (neutral-900)
  cursor: "#52514e",
};

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

interface ChartPoint {
  date: string;
  /** Portfolio market value (patrimony). */
  wealth: number;
  /** Cumulative contributions (invested capital base). */
  capital: number;
  /** Cumulative proventos received. */
  proventos: number;
  /** Market gain/loss = wealth − capital. */
  gain: number;
  /** Range for the shaded gap area: [capital, wealth]. */
  band: [number, number];
}

const MONTHS_PT = [
  "jan",
  "fev",
  "mar",
  "abr",
  "mai",
  "jun",
  "jul",
  "ago",
  "set",
  "out",
  "nov",
  "dez",
];

/** Parse an ISO `YYYY-MM-DD` as local time (mirrors `lib/format` to avoid TZ shifts). */
function parseISODate(value: string): Date {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(value);
  if (m) return new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
  return new Date(value);
}

/** Epoch cutoff for a period preset, anchored to `as_of` (not the wall clock). */
function periodCutoff(asOf: string, period: Period): number | null {
  if (period === "all") return null;
  const d = parseISODate(asOf);
  if (period === "ytd") return new Date(d.getFullYear(), 0, 1).getTime();
  const oneYearBack = new Date(d);
  oneYearBack.setFullYear(d.getFullYear() - 1);
  return oneYearBack.getTime();
}

/** Bucket key for the Monday of a date's ISO week. */
function weekKey(d: Date): string {
  const monday = new Date(d);
  const dow = (d.getDay() + 6) % 7; // Monday = 0
  monday.setDate(d.getDate() - dow);
  return `${monday.getFullYear()}-${monday.getMonth()}-${monday.getDate()}`;
}

/**
 * Filter by period, then downsample by granularity. Every field is a cumulative
 * stock (market value, contributions, proventos), so taking the LAST observation
 * per bucket is the correct aggregation — no synthetic dates are introduced.
 */
function buildChartData(
  points: EvolutionPointOut[],
  granularity: EvolutionGranularity,
  period: Period,
  asOf: string,
): ChartPoint[] {
  const sorted = [...points].sort((a, b) =>
    a.date < b.date ? -1 : a.date > b.date ? 1 : 0,
  );
  const cutoff = periodCutoff(asOf, period);
  const filtered =
    cutoff == null
      ? sorted
      : sorted.filter((p) => parseISODate(p.date).getTime() >= cutoff);

  let sampled = filtered;
  if (granularity !== "daily") {
    const byBucket = new Map<string, EvolutionPointOut>();
    for (const p of filtered) {
      const key =
        granularity === "monthly"
          ? p.date.slice(0, 7)
          : weekKey(parseISODate(p.date));
      byBucket.set(key, p); // last observation in the bucket wins
    }
    sampled = Array.from(byBucket.values());
  }

  return sampled.map((p) => {
    const gain = p.market_value - p.contributions;
    return {
      date: p.date,
      wealth: p.market_value,
      capital: p.contributions,
      proventos: p.proventos,
      gain,
      band: [p.contributions, p.market_value] as [number, number],
    };
  });
}

const brlCompact = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  notation: "compact",
  maximumFractionDigits: 1,
});

function formatAxisDate(value: string, granularity: EvolutionGranularity): string {
  const d = parseISODate(value);
  if (granularity === "monthly") {
    return `${MONTHS_PT[d.getMonth()]}/${String(d.getFullYear()).slice(2)}`;
  }
  return `${String(d.getDate()).padStart(2, "0")}/${String(
    d.getMonth() + 1,
  ).padStart(2, "0")}`;
}

/* ── Tooltips & legend ───────────────────────────────────────────────────── */

interface TooltipEntry {
  payload: ChartPoint;
}

function TooltipRow({
  color,
  label,
  value,
  valueClass,
}: {
  color: string;
  label: string;
  value: string;
  valueClass?: string;
}) {
  return (
    <div className="flex items-center justify-between gap-6">
      <span className="flex items-center gap-1.5 text-neutral-500 dark:text-neutral-400">
        <span
          aria-hidden
          className="inline-block h-2 w-2 rounded-full"
          style={{ backgroundColor: color }}
        />
        {label}
      </span>
      <span
        className={clsx(
          "font-semibold tabular-nums",
          valueClass ?? "text-neutral-800 dark:text-neutral-100",
        )}
      >
        {value}
      </span>
    </div>
  );
}

function PatrimonyTooltip({
  active,
  payload,
  palette,
  gainColor,
  showProventos,
}: {
  active?: boolean;
  payload?: TooltipEntry[];
  palette: ChartPalette;
  gainColor: string;
  showProventos: boolean;
}) {
  if (!active || !payload || payload.length === 0) return null;
  const p = payload[0].payload;
  const gainClass =
    p.gain > 0
      ? "text-emerald-600 dark:text-emerald-400"
      : p.gain < 0
        ? "text-rose-600 dark:text-rose-400"
        : "text-neutral-800 dark:text-neutral-100";
  return (
    <div className="rounded-lg border border-neutral-200 bg-white px-3 py-2 text-xs shadow-md dark:border-neutral-700 dark:bg-neutral-900">
      <div className="mb-1.5 font-semibold text-neutral-800 dark:text-neutral-100">
        {formatDate(p.date)}
      </div>
      <div className="space-y-1">
        <TooltipRow
          color={palette.patrimony}
          label="Patrimônio"
          value={formatBRL(p.wealth)}
        />
        <TooltipRow
          color={palette.contributions}
          label="Aportes"
          value={formatBRL(p.capital)}
        />
        <TooltipRow
          color={gainColor}
          label="Ganho de mercado"
          value={formatBRL(p.gain)}
          valueClass={gainClass}
        />
        {showProventos && (
          <TooltipRow
            color={palette.proventos}
            label="Proventos"
            value={formatBRL(p.proventos)}
          />
        )}
      </div>
    </div>
  );
}

function ProventosTooltip({
  active,
  payload,
  palette,
}: {
  active?: boolean;
  payload?: TooltipEntry[];
  palette: ChartPalette;
}) {
  if (!active || !payload || payload.length === 0) return null;
  const p = payload[0].payload;
  return (
    <div className="rounded-lg border border-neutral-200 bg-white px-3 py-2 text-xs shadow-md dark:border-neutral-700 dark:bg-neutral-900">
      <div className="mb-1.5 font-semibold text-neutral-800 dark:text-neutral-100">
        {formatDate(p.date)}
      </div>
      <TooltipRow
        color={palette.proventos}
        label="Proventos acumulados"
        value={formatBRL(p.proventos)}
      />
    </div>
  );
}

/**
 * Custom legend so identity never rides color alone: lines get a line-key,
 * the shaded gap gets a filled square, all labels in muted text ink.
 */
function PatrimonyLegend({
  palette,
  gainColor,
}: {
  palette: ChartPalette;
  gainColor: string;
}) {
  const items: { label: string; color: string; kind: "line" | "area" }[] = [
    { label: "Patrimônio", color: palette.patrimony, kind: "line" },
    { label: "Aportes acumulados", color: palette.contributions, kind: "line" },
    { label: "Ganho de mercado", color: gainColor, kind: "area" },
  ];
  return (
    <ul className="flex flex-wrap items-center justify-center gap-x-5 gap-y-1 pt-3 text-xs">
      {items.map((it) => (
        <li
          key={it.label}
          className="flex items-center gap-1.5 text-neutral-600 dark:text-neutral-300"
        >
          {it.kind === "line" ? (
            <span
              aria-hidden
              className="inline-block h-0.5 w-4 rounded-full"
              style={{ backgroundColor: it.color }}
            />
          ) : (
            <span
              aria-hidden
              className="inline-block h-2.5 w-2.5 rounded-sm"
              style={{ backgroundColor: it.color, opacity: 0.55 }}
            />
          )}
          {it.label}
        </li>
      ))}
    </ul>
  );
}

/* ── Chart ───────────────────────────────────────────────────────────────── */

/**
 * Patrimony evolution (task 10). A patrimony line vs. a cumulative-contributions
 * line with the gap between them shaded as market gain/loss, an optional
 * cumulative-proventos small multiple, and a collapsible data table (the
 * accessible fallback for the visual). Colors are theme-aware and CVD-safe.
 */
export function EvolutionPagePatrimonyChart({
  points,
  granularity,
  period,
  asOf,
}: EvolutionPagePatrimonyChartProps) {
  const dark = usePrefersDark();
  const palette = dark ? DARK : LIGHT;

  const data = useMemo(
    () => buildChartData(points, granularity, period, asOf),
    [points, granularity, period, asOf],
  );

  if (data.length === 0) {
    return (
      <p className="py-12 text-center text-sm text-neutral-500 dark:text-neutral-400">
        Nenhum ponto no período selecionado.
      </p>
    );
  }

  const lastGain = data[data.length - 1].gain;
  const gainColor = lastGain >= 0 ? palette.gainPos : palette.gainNeg;
  const hasProventos = data.some((p) => p.proventos > 0);
  const axisTick = { fill: palette.axis, fontSize: 12 };
  const soloDot = data.length === 1;

  return (
    <div className="space-y-6">
      <figure className="m-0">
        <div className="h-[22rem] w-full">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart
              data={data}
              margin={{ top: 8, right: 12, bottom: 4, left: 4 }}
            >
              <CartesianGrid vertical={false} stroke={palette.grid} strokeWidth={1} />
              <XAxis
                dataKey="date"
                tickFormatter={(v: string) => formatAxisDate(v, granularity)}
                tick={axisTick}
                tickLine={false}
                axisLine={{ stroke: palette.grid }}
                minTickGap={28}
                interval="preserveStartEnd"
              />
              <YAxis
                tickFormatter={(v: number) => brlCompact.format(v)}
                tick={axisTick}
                tickLine={false}
                axisLine={false}
                width={72}
              />
              <Tooltip
                content={
                  <PatrimonyTooltip
                    palette={palette}
                    gainColor={gainColor}
                    showProventos={hasProventos}
                  />
                }
                cursor={{ stroke: palette.cursor, strokeWidth: 1 }}
              />
              <Legend content={<PatrimonyLegend palette={palette} gainColor={gainColor} />} />
              {/* Shaded gap = market gain/loss (drawn behind the lines). */}
              <Area
                dataKey="band"
                name="Ganho de mercado"
                stroke="none"
                fill={gainColor}
                fillOpacity={0.18}
                activeDot={false}
                isAnimationActive={false}
              />
              <Line
                dataKey="capital"
                name="Aportes acumulados"
                type="linear"
                stroke={palette.contributions}
                strokeWidth={2}
                dot={soloDot ? { r: 3 } : false}
                activeDot={{
                  r: 4,
                  strokeWidth: 2,
                  stroke: palette.surface,
                  fill: palette.contributions,
                }}
                isAnimationActive={false}
              />
              <Line
                dataKey="wealth"
                name="Patrimônio"
                type="linear"
                stroke={palette.patrimony}
                strokeWidth={2}
                dot={soloDot ? { r: 3 } : false}
                activeDot={{
                  r: 4,
                  strokeWidth: 2,
                  stroke: palette.surface,
                  fill: palette.patrimony,
                }}
                isAnimationActive={false}
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
        <figcaption className="mt-3 text-xs text-neutral-500 dark:text-neutral-400">
          A área sombreada entre os aportes acumulados e o patrimônio é o ganho (ou
          perda) de mercado.
        </figcaption>
      </figure>

      {hasProventos && (
        <figure className="m-0">
          <figcaption className="mb-2 text-xs font-medium uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
            Proventos acumulados
          </figcaption>
          <div className="h-36 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart
                data={data}
                margin={{ top: 4, right: 12, bottom: 4, left: 4 }}
              >
                <CartesianGrid vertical={false} stroke={palette.grid} strokeWidth={1} />
                <XAxis
                  dataKey="date"
                  tickFormatter={(v: string) => formatAxisDate(v, granularity)}
                  tick={axisTick}
                  tickLine={false}
                  axisLine={{ stroke: palette.grid }}
                  minTickGap={28}
                  interval="preserveStartEnd"
                />
                <YAxis
                  tickFormatter={(v: number) => brlCompact.format(v)}
                  tick={axisTick}
                  tickLine={false}
                  axisLine={false}
                  width={72}
                />
                <Tooltip
                  content={<ProventosTooltip palette={palette} />}
                  cursor={{ stroke: palette.cursor, strokeWidth: 1 }}
                />
                <Area
                  dataKey="proventos"
                  name="Proventos acumulados"
                  type="linear"
                  stroke={palette.proventos}
                  strokeWidth={2}
                  fill={palette.proventos}
                  fillOpacity={0.14}
                  dot={soloDot ? { r: 3 } : false}
                  activeDot={{
                    r: 4,
                    strokeWidth: 2,
                    stroke: palette.surface,
                    fill: palette.proventos,
                  }}
                  isAnimationActive={false}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </figure>
      )}

      <details className="rounded-lg border border-neutral-200 dark:border-neutral-800">
        <summary className="cursor-pointer px-3 py-2 text-xs font-medium text-neutral-600 dark:text-neutral-300">
          Ver dados da série ({data.length} pontos)
        </summary>
        <div className="max-h-80 overflow-auto border-t border-neutral-200 dark:border-neutral-800">
          <table className="w-full text-left text-xs tabular-nums">
            <thead className="sticky top-0 bg-neutral-50 dark:bg-neutral-950">
              <tr className="text-neutral-500 dark:text-neutral-400">
                <th className="px-3 py-2 font-medium">Data</th>
                <th className="px-3 py-2 text-right font-medium">Patrimônio</th>
                <th className="px-3 py-2 text-right font-medium">Aportes</th>
                <th className="px-3 py-2 text-right font-medium">Ganho</th>
                {hasProventos && (
                  <th className="px-3 py-2 text-right font-medium">Proventos</th>
                )}
              </tr>
            </thead>
            <tbody>
              {data.map((p) => (
                <tr
                  key={p.date}
                  className="border-t border-neutral-100 dark:border-neutral-800/60"
                >
                  <td className="px-3 py-1.5 text-neutral-700 dark:text-neutral-200">
                    {formatDate(p.date)}
                  </td>
                  <td className="px-3 py-1.5 text-right text-neutral-700 dark:text-neutral-200">
                    {formatBRL(p.wealth)}
                  </td>
                  <td className="px-3 py-1.5 text-right text-neutral-700 dark:text-neutral-200">
                    {formatBRL(p.capital)}
                  </td>
                  <td
                    className={clsx(
                      "px-3 py-1.5 text-right",
                      p.gain >= 0
                        ? "text-emerald-600 dark:text-emerald-400"
                        : "text-rose-600 dark:text-rose-400",
                    )}
                  >
                    {formatBRL(p.gain)}
                  </td>
                  {hasProventos && (
                    <td className="px-3 py-1.5 text-right text-neutral-700 dark:text-neutral-200">
                      {formatBRL(p.proventos)}
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  );
}
