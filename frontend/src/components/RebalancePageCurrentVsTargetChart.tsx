import { useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  type TooltipProps,
} from "recharts";

import { formatPct } from "../lib/format";

/** One asset row for the current-vs-target comparison chart. */
export interface CurrentVsTargetDatum {
  key: string;
  /** Current weight in the portfolio, in percent units. */
  current: number;
  /** Desired weight, in percent units. */
  target: number;
}

interface CurrentVsTargetChartProps {
  data: CurrentVsTargetDatum[];
}

/**
 * Tracks the OS/browser colour-scheme so Recharts (which needs real colour
 * strings for its SVG marks) matches the app's `prefers-color-scheme` theming.
 */
function usePrefersDark(): boolean {
  const [dark, setDark] = useState(
    () =>
      typeof window !== "undefined" &&
      window.matchMedia("(prefers-color-scheme: dark)").matches,
  );

  useEffect(() => {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const handler = (event: MediaQueryListEvent) => setDark(event.matches);
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, []);

  return dark;
}

/**
 * Grouped horizontal bars comparing each asset's **current** weight (blue,
 * categorical slot 1) against its **target** weight (aqua, slot 2). Colours are
 * the data-viz reference palette, validated colourblind-safe in both modes; the
 * legend + the rebalance table below carry identity so colour is never the only
 * cue (aqua sits just under 3:1 on the light surface — relief satisfied).
 */
export function RebalancePageCurrentVsTargetChart({
  data,
}: CurrentVsTargetChartProps) {
  const dark = usePrefersDark();

  const palette = dark
    ? {
        current: "#3987e5",
        target: "#199e70",
        grid: "#2c2c2a",
        axis: "#898781",
        surface: "#1a1a19",
        border: "rgba(255,255,255,0.14)",
        text: "#c3c2b7",
        cursor: "rgba(255,255,255,0.06)",
      }
    : {
        current: "#2a78d6",
        target: "#1baf7a",
        grid: "#e1e0d9",
        axis: "#898781",
        surface: "#fcfcfb",
        border: "rgba(11,11,11,0.12)",
        text: "#52514e",
        cursor: "rgba(11,11,11,0.04)",
      };

  const height = Math.max(data.length * 52 + 56, 200);

  const renderTooltip = ({
    active,
    payload,
    label,
  }: TooltipProps<number, string>) => {
    if (!active || !payload || payload.length === 0) return null;
    return (
      <div
        className="rounded-lg px-3 py-2 text-xs shadow-lg"
        style={{
          background: palette.surface,
          border: `1px solid ${palette.border}`,
          color: palette.text,
        }}
      >
        <p className="mb-1 font-semibold" style={{ color: palette.text }}>
          {label}
        </p>
        {payload.map((entry, index) => (
          <p key={index} className="flex items-center gap-2 tabular-nums">
            <span
              aria-hidden
              className="inline-block h-2.5 w-2.5 rounded-sm"
              style={{ background: entry.color }}
            />
            <span>{entry.name}</span>
            <span className="ml-auto font-medium">
              {formatPct(typeof entry.value === "number" ? entry.value : null)}
            </span>
          </p>
        ))}
      </div>
    );
  };

  return (
    <div style={{ width: "100%", height }}>
      <ResponsiveContainer>
        <BarChart
          layout="vertical"
          data={data}
          margin={{ top: 4, right: 16, bottom: 16, left: 8 }}
          barCategoryGap="24%"
          barGap={2}
        >
          <CartesianGrid
            horizontal={false}
            stroke={palette.grid}
            strokeDasharray="3 3"
          />
          <XAxis
            type="number"
            unit="%"
            tick={{ fill: palette.axis, fontSize: 12 }}
            tickLine={false}
            axisLine={{ stroke: palette.grid }}
            label={{
              value: "Peso (%)",
              position: "insideBottom",
              offset: -8,
              fill: palette.axis,
              fontSize: 12,
            }}
          />
          <YAxis
            type="category"
            dataKey="key"
            width={84}
            tick={{ fill: palette.axis, fontSize: 12 }}
            tickLine={false}
            axisLine={{ stroke: palette.grid }}
          />
          <Tooltip<number, string>
            content={renderTooltip}
            cursor={{ fill: palette.cursor }}
          />
          <Legend
            wrapperStyle={{ fontSize: 12, color: palette.text, paddingTop: 4 }}
          />
          <Bar
            dataKey="current"
            name="Atual"
            fill={palette.current}
            radius={[0, 4, 4, 0]}
            maxBarSize={16}
          />
          <Bar
            dataKey="target"
            name="Meta"
            fill={palette.target}
            radius={[0, 4, 4, 0]}
            maxBarSize={16}
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
