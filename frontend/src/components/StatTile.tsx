import type { ReactNode } from "react";
import clsx from "clsx";

import { Card } from "./Card";

interface StatTileProps {
  label: string;
  value: ReactNode;
  /** Secondary line, e.g. a delta or context. */
  hint?: ReactNode;
  /** Colors the hint: up=green, down=red, neutral=muted. */
  trend?: "up" | "down" | "neutral";
}

/** A single headline metric. Used across the Dashboard and Evolution screens. */
export function StatTile({ label, value, hint, trend = "neutral" }: StatTileProps) {
  return (
    <Card>
      <p className="text-xs font-medium uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
        {label}
      </p>
      <p className="mt-1 text-2xl font-semibold tabular-nums text-neutral-900 dark:text-neutral-50">
        {value}
      </p>
      {hint != null && (
        <p
          className={clsx(
            "mt-1 text-sm tabular-nums",
            trend === "up" && "text-emerald-600 dark:text-emerald-400",
            trend === "down" && "text-rose-600 dark:text-rose-400",
            trend === "neutral" && "text-neutral-500 dark:text-neutral-400",
          )}
        >
          {hint}
        </p>
      )}
    </Card>
  );
}
