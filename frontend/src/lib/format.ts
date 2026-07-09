/**
 * Shared pt-BR formatting helpers (README §7). Use these everywhere money,
 * percentages, or dates render so the UI stays consistent.
 */

const EMPTY = "—";

const brl = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const pct = new Intl.NumberFormat("pt-BR", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const dateFmt = new Intl.DateTimeFormat("pt-BR", {
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
});

/** `1234.56` → `R$ 1.234,56`. Nullish/NaN → `—`. */
export function formatBRL(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return EMPTY;
  return brl.format(value);
}

/**
 * A percent value (already in percent units, e.g. `12.34`) → `12,34%`.
 * `signed` prefixes a `+` for positive values (useful for returns). Nullish/NaN → `—`.
 */
export function formatPct(
  value: number | null | undefined,
  options?: { signed?: boolean },
): string {
  if (value == null || Number.isNaN(value)) return EMPTY;
  const sign = options?.signed && value > 0 ? "+" : "";
  return `${sign}${pct.format(value)}%`;
}

/**
 * ISO date/datetime string (or `Date`) → `DD/MM/YYYY`. Date-only strings are
 * parsed as local time to avoid off-by-one shifts across time zones. Nullish/
 * invalid → `—`.
 */
export function formatDate(value: string | Date | null | undefined): string {
  if (value == null || value === "") return EMPTY;

  let date: Date;
  if (value instanceof Date) {
    date = value;
  } else {
    const dateOnly = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
    if (dateOnly) {
      date = new Date(
        Number(dateOnly[1]),
        Number(dateOnly[2]) - 1,
        Number(dateOnly[3]),
      );
    } else {
      date = new Date(value);
    }
  }

  if (Number.isNaN(date.getTime())) return EMPTY;
  return dateFmt.format(date);
}
