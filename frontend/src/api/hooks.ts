import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  apiDelete,
  apiDownload,
  apiGet,
  apiPatch,
  apiPost,
  apiPut,
  apiUpload,
} from "./client";
import type {
  AccountingView,
  ClearSupersededResponse,
  CnpjOverrideIn,
  CnpjOverrideResult,
  EvolutionView,
  HealthResponse,
  ImportKind,
  ImportStatus,
  ImportSummary,
  JobsStatus,
  LatestQuotes,
  PortfolioView,
  RebalanceView,
  RefreshResult,
  RunDailyResult,
  TargetsResponse,
  TargetsUpdate,
  Trade,
  TradeInput,
  TradeListResponse,
  TradeOrigin,
  TradeUpdate,
} from "./types";

/** Central registry of React Query keys so hooks and invalidations stay in sync. */
export const queryKeys = {
  health: ["health"] as const,
  positions: ["positions"] as const,
  evolution: ["evolution"] as const,
  rebalance: (contribution?: number) =>
    ["rebalance", contribution ?? 0] as const,
  targets: ["targets"] as const,
  accounting: ["accounting", "bens-e-direitos"] as const,
  importStatus: ["imports", "status"] as const,
  latestQuotes: ["quotes", "latest"] as const,
  trades: (origin?: TradeOrigin) => ["trades", origin ?? "manual"] as const,
  jobsStatus: ["jobs", "status"] as const,
};

/* ── Queries ─────────────────────────────────────────────────────────────── */

/** `GET /api/health` — used to verify backend connectivity. */
export function useHealth() {
  return useQuery({
    queryKey: queryKeys.health,
    queryFn: () => apiGet<HealthResponse>("/api/health"),
  });
}

/** `GET /api/portfolio/positions` — holdings + allocation. */
export function usePositions() {
  return useQuery({
    queryKey: queryKeys.positions,
    queryFn: () => apiGet<PortfolioView>("/api/portfolio/positions"),
  });
}

/** `GET /api/portfolio/evolution` — equity curve + return metrics. */
export function useEvolution() {
  return useQuery({
    queryKey: queryKeys.evolution,
    queryFn: () => apiGet<EvolutionView>("/api/portfolio/evolution"),
  });
}

/** `GET /api/portfolio/rebalance?contribution=` — current vs. target + buys. */
export function useRebalance(contribution?: number) {
  return useQuery({
    queryKey: queryKeys.rebalance(contribution),
    queryFn: () =>
      apiGet<RebalanceView>(
        "/api/portfolio/rebalance",
        contribution != null ? { contribution } : undefined,
      ),
  });
}

/** `GET /api/targets` — saved targets grouped by kind. */
export function useTargets() {
  return useQuery({
    queryKey: queryKeys.targets,
    queryFn: () => apiGet<TargetsResponse>("/api/targets"),
  });
}

/** `GET /api/accounting/bens-e-direitos` — DIRPF preview rows. */
export function useAccounting() {
  return useQuery({
    queryKey: queryKeys.accounting,
    queryFn: () =>
      apiGet<AccountingView>("/api/accounting/bens-e-direitos"),
  });
}

/**
 * Non-hook helper: download the Bens e Direitos sheet as `.xlsx`
 * (`GET /api/accounting/bens-e-direitos.xlsx`).
 */
export function downloadAccountingXlsx(): Promise<void> {
  return apiDownload(
    "/api/accounting/bens-e-direitos.xlsx",
    "bens-e-direitos.xlsx",
  );
}

/** `GET /api/imports/status` — what has been imported so far. */
export function useImportStatus() {
  return useQuery({
    queryKey: queryKeys.importStatus,
    queryFn: () => apiGet<ImportStatus>("/api/imports/status"),
  });
}

/** `GET /api/quotes/latest` — a `{ ticker: LatestQuote }` map. */
export function useLatestQuotes() {
  return useQuery({
    queryKey: queryKeys.latestQuotes,
    queryFn: () => apiGet<LatestQuotes>("/api/quotes/latest"),
  });
}

/** `GET /api/trades?origin=` — trades newest-first (default `manual`). */
export function useTrades(origin?: TradeOrigin) {
  return useQuery({
    queryKey: queryKeys.trades(origin),
    queryFn: () =>
      apiGet<TradeListResponse>(
        "/api/trades",
        origin != null ? { origin } : undefined,
      ),
  });
}

/** `GET /api/jobs/status` — data-freshness header payload. */
export function useJobsStatus() {
  return useQuery({
    queryKey: queryKeys.jobsStatus,
    queryFn: () => apiGet<JobsStatus>("/api/jobs/status"),
  });
}

/* ── Mutations ───────────────────────────────────────────────────────────── */

/** `POST /api/quotes/refresh` — refresh cached quotes, then refetch views. */
export function useRefreshQuotes() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => apiPost<RefreshResult>("/api/quotes/refresh"),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.positions });
      void qc.invalidateQueries({ queryKey: queryKeys.evolution });
      void qc.invalidateQueries({ queryKey: ["rebalance"] });
      void qc.invalidateQueries({ queryKey: queryKeys.latestQuotes });
    },
  });
}

/** `POST /api/import/{kind}` — upload a B3 Excel export (multipart `file`). */
export function useImportFile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ kind, file }: { kind: ImportKind; file: File }) =>
      apiUpload<ImportSummary>(`/api/import/${kind}`, file),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.importStatus });
      void qc.invalidateQueries({ queryKey: queryKeys.positions });
      void qc.invalidateQueries({ queryKey: queryKeys.evolution });
      void qc.invalidateQueries({ queryKey: ["trades"] });
    },
  });
}

/** `PUT /api/targets` — replace all stored targets. */
export function useSaveTargets() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (targets: TargetsUpdate) =>
      apiPut<TargetsResponse>("/api/targets", targets),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.targets });
      void qc.invalidateQueries({ queryKey: ["rebalance"] });
    },
  });
}

/** `POST /api/accounting/cnpj-overrides` — persist ticker→CNPJ overrides. */
export function useSaveCnpj() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (rows: CnpjOverrideIn[]) =>
      apiPost<CnpjOverrideResult>("/api/accounting/cnpj-overrides", rows),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.accounting });
    },
  });
}

/** `POST /api/trades` — create a manual trade. */
export function useAddTrade() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (trade: TradeInput) => apiPost<Trade>("/api/trades", trade),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["trades"] });
      void qc.invalidateQueries({ queryKey: queryKeys.positions });
      void qc.invalidateQueries({ queryKey: queryKeys.evolution });
    },
  });
}

/** `PATCH /api/trades/{trade_id}` — edit a manual trade. */
export function useEditTrade() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      tradeId,
      update,
    }: {
      tradeId: number;
      update: TradeUpdate;
    }) => apiPatch<Trade>(`/api/trades/${tradeId}`, update),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["trades"] });
      void qc.invalidateQueries({ queryKey: queryKeys.positions });
      void qc.invalidateQueries({ queryKey: queryKeys.evolution });
    },
  });
}

/** `DELETE /api/trades/{trade_id}` — delete a manual trade. */
export function useDeleteTrade() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (tradeId: number) =>
      apiDelete<void>(`/api/trades/${tradeId}`),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["trades"] });
      void qc.invalidateQueries({ queryKey: queryKeys.positions });
      void qc.invalidateQueries({ queryKey: queryKeys.evolution });
    },
  });
}

/** `POST /api/trades/clear-superseded` — drop manual trades now covered by a re-import. */
export function useClearSuperseded() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiPost<ClearSupersededResponse>("/api/trades/clear-superseded"),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["trades"] });
      void qc.invalidateQueries({ queryKey: queryKeys.positions });
      void qc.invalidateQueries({ queryKey: queryKeys.evolution });
    },
  });
}

/** `POST /api/jobs/run-daily` — trigger the daily quote refresh + snapshot. */
export function useRunDaily() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => apiPost<RunDailyResult>("/api/jobs/run-daily"),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.positions });
      void qc.invalidateQueries({ queryKey: queryKeys.evolution });
      void qc.invalidateQueries({ queryKey: ["rebalance"] });
      void qc.invalidateQueries({ queryKey: queryKeys.latestQuotes });
      void qc.invalidateQueries({ queryKey: queryKeys.jobsStatus });
    },
  });
}
