import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiGet, apiPost, apiPut, apiUpload } from "./client";
import type {
  AccountingView,
  CnpjOverride,
  EvolutionView,
  HealthResponse,
  ImportResult,
  ImportStatus,
  PortfolioView,
  RebalanceView,
  RefreshResult,
  TargetAllocation,
} from "./types";

/** Central registry of React Query keys so hooks and invalidations stay in sync. */
export const queryKeys = {
  health: ["health"] as const,
  positions: ["positions"] as const,
  evolution: ["evolution"] as const,
  rebalance: ["rebalance"] as const,
  targets: ["targets"] as const,
  accounting: (year?: number) => ["accounting", year ?? null] as const,
  importStatus: ["import", "status"] as const,
};

/* ── Queries ─────────────────────────────────────────────────────────────── */

/** `GET /api/health` — used to verify backend connectivity. */
export function useHealth() {
  return useQuery({
    queryKey: queryKeys.health,
    queryFn: () => apiGet<HealthResponse>("/api/health"),
  });
}

/** `GET /api/portfolio/positions` — holdings + allocation (task 04). */
export function usePositions() {
  return useQuery({
    queryKey: queryKeys.positions,
    queryFn: () => apiGet<PortfolioView>("/api/portfolio/positions"),
  });
}

/** `GET /api/portfolio/evolution` — patrimony curve + rentability (task 05). */
export function useEvolution() {
  return useQuery({
    queryKey: queryKeys.evolution,
    queryFn: () => apiGet<EvolutionView>("/api/portfolio/evolution"),
  });
}

/** `GET /api/portfolio/rebalance` — current vs. target + buy suggestions (task 06). */
export function useRebalance() {
  return useQuery({
    queryKey: queryKeys.rebalance,
    queryFn: () => apiGet<RebalanceView>("/api/portfolio/rebalance"),
  });
}

/** `GET /api/portfolio/targets` — saved target allocations (task 06). */
export function useTargets() {
  return useQuery({
    queryKey: queryKeys.targets,
    queryFn: () => apiGet<TargetAllocation[]>("/api/portfolio/targets"),
  });
}

/** `GET /api/accounting/bens-direitos` — DIRPF rows for a year (task 07). */
export function useAccounting(year?: number) {
  return useQuery({
    queryKey: queryKeys.accounting(year),
    queryFn: () =>
      apiGet<AccountingView>(
        "/api/accounting/bens-direitos",
        year != null ? { year } : undefined,
      ),
  });
}

/** `GET /api/import/status` — what has been imported so far (task 02). */
export function useImportStatus() {
  return useQuery({
    queryKey: queryKeys.importStatus,
    queryFn: () => apiGet<ImportStatus>("/api/import/status"),
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
      void qc.invalidateQueries({ queryKey: queryKeys.rebalance });
    },
  });
}

/** `POST /api/import` — upload a B3 Excel export (task 02). */
export function useImportFile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => apiUpload<ImportResult>("/api/import", file),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.importStatus });
      void qc.invalidateQueries({ queryKey: queryKeys.positions });
      void qc.invalidateQueries({ queryKey: queryKeys.evolution });
    },
  });
}

/** `PUT /api/portfolio/targets` — save target allocations (task 06). */
export function useSaveTargets() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (targets: TargetAllocation[]) =>
      apiPut<TargetAllocation[]>("/api/portfolio/targets", targets),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.targets });
      void qc.invalidateQueries({ queryKey: queryKeys.rebalance });
    },
  });
}

/** `PUT /api/accounting/cnpj` — override a ticker→CNPJ mapping (task 07/12). */
export function useSaveCnpj() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (override: CnpjOverride) =>
      apiPut<CnpjOverride>("/api/accounting/cnpj", override),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["accounting"] });
    },
  });
}
