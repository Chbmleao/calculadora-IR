/**
 * TypeScript mirrors of the backend Pydantic response schemas.
 *
 * Money fields are plain `number`s already rounded to 2dp by the backend
 * (README §7); percentages are expressed in percent units (e.g. `40` = 40%).
 * Dates are ISO strings (`YYYY-MM-DD`); datetimes are ISO 8601.
 *
 * Domain endpoints (positions, evolution, rebalance, accounting, import) are
 * implemented by tasks 04-07/02; keep these types in sync with `app/schemas.py`
 * and the per-domain schema modules as those land.
 */

/* ── Foundation (app/schemas.py) ─────────────────────────────────────────── */

export interface HealthResponse {
  status: string;
}

/** Standard error envelope: `{ "error": "message" }` (README §7). */
export interface ErrorResponse {
  error: string;
}

/* ── Positions & allocation (task 04) ────────────────────────────────────── */

/** Asset class as classified from the ticker suffix (README §4). */
export type AssetClass = "Ação" | "FII" | "ETF" | "BDR" | (string & {});

export interface Position {
  ticker: string;
  asset_class: AssetClass;
  quantity: number;
  /** Average purchase price = cost basis per share. */
  avg_price: number;
  /** Total cost basis (quantity × avg_price). */
  cost: number;
  /** Latest cached close, or `null` when no quote is available. */
  last_price: number | null;
  market_value: number;
  /** Weight of this position in the portfolio, in percent. */
  weight_pct: number;
  /** Unrealized gain/loss (market_value − cost). */
  gain: number;
  gain_pct: number;
  /** ISO date of the quote behind `last_price`. */
  quote_date: string | null;
}

export interface AllocationSlice {
  /** Ticker or asset-class name. */
  key: string;
  label: string;
  market_value: number;
  weight_pct: number;
}

export interface PortfolioView {
  /** ISO date of the most recent quote used, or `null` if none. */
  as_of: string | null;
  total_value: number;
  total_cost: number;
  total_gain: number;
  total_gain_pct: number;
  positions: Position[];
  by_class: AllocationSlice[];
}

/* ── Evolution & rentability (task 05) ───────────────────────────────────── */

export interface EvolutionPoint {
  /** ISO date of the snapshot. */
  date: string;
  total_value: number;
  /** Money added by the investor up to this date. */
  contributions_to_date: number;
  cumulative_proventos: number;
  /** Cost basis invested to date. */
  invested: number;
}

export interface EvolutionMetrics {
  start_date: string | null;
  end_date: string | null;
  total_value: number;
  total_contributions: number;
  cumulative_proventos: number;
  /** Simple absolute return, in percent. */
  simple_return_pct: number;
  /** Time-weighted return (removes contribution timing), in percent. */
  twr_pct: number;
}

export interface EvolutionView {
  points: EvolutionPoint[];
  metrics: EvolutionMetrics;
}

/* ── Target allocation & rebalancing (task 06) ───────────────────────────── */

export type TargetKind = "ticker" | "class";

export interface TargetAllocation {
  kind: TargetKind;
  /** Ticker (kind='ticker') or asset-class name (kind='class'). */
  key: string;
  target_pct: number;
}

export type RebalanceAction = "buy" | "sell" | "hold";

export interface RebalanceRow {
  key: string;
  label: string;
  current_value: number;
  current_pct: number;
  target_pct: number;
  target_value: number;
  /** Amount to move: positive = buy, negative = sell. */
  delta_value: number;
  suggested_action: RebalanceAction;
}

export interface RebalanceView {
  total_value: number;
  rows: RebalanceRow[];
  targets: TargetAllocation[];
}

/* ── Accounting — Bens e Direitos (task 07) ──────────────────────────────── */

export interface AccountingRow {
  /** DIRPF group, e.g. "03 - Participações Societárias". */
  group: string;
  code: string;
  ticker: string;
  cnpj: string | null;
  discrimination: string;
  quantity: number;
  /** Situação em 31/12 do ano anterior. */
  situation_prev: number;
  /** Situação em 31/12 do ano-base. */
  situation_current: number;
}

export interface AccountingView {
  year: number;
  rows: AccountingRow[];
}

/** CNPJ override saved back to the legacy catalog (task 07/12). */
export interface CnpjOverride {
  ticker: string;
  cnpj: string;
}

/* ── Ingestion / import (task 02) ────────────────────────────────────────── */

export type ImportKind =
  | "negotiation_summary"
  | "proventos"
  | "negotiation_history"
  | "catalog";

export interface ImportedFile {
  filename: string;
  kind: ImportKind | (string & {});
  rows: number;
  /** ISO datetime the file was imported. */
  imported_at: string;
}

export interface ImportStatus {
  /** ISO datetime of the most recent import, or `null` if none yet. */
  last_import: string | null;
  files: ImportedFile[];
  transactions: number;
  positions: number;
  proventos: number;
}

export interface ImportResult {
  kind: string;
  filename: string;
  rows_imported: number;
  message: string;
}

/* ── Quotes (task 03/13) ─────────────────────────────────────────────────── */

export interface RefreshResult {
  /** Number of quotes refreshed. */
  updated: number;
  /** ISO date the quotes are now current to. */
  as_of: string | null;
  message: string;
}
