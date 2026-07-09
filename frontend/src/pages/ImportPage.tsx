import { useMemo, useState } from "react";
import clsx from "clsx";
import { useQueryClient } from "@tanstack/react-query";

import { extractErrorMessage } from "../api/client";
import {
  queryKeys,
  useClearSuperseded,
  useImportStatus,
  usePositions,
  useTrades,
} from "../api/hooks";
import type { ImportKind, ImportStatus, TradeOrigin } from "../api/types";
import { Card } from "../components/Card";
import { EmptyState } from "../components/EmptyState";
import { ErrorBanner } from "../components/ErrorBanner";
import { ImportPageTradeForm } from "../components/ImportPageTradeForm";
import { ImportPageTradesTable } from "../components/ImportPageTradesTable";
import { ImportPageUploadCard } from "../components/ImportPageUploadCard";
import { LoadingSpinner } from "../components/LoadingSpinner";
import { PageHeader } from "../components/PageHeader";
import { formatDate } from "../lib/format";
import { useToast } from "../lib/toast";

const TICKER_DATALIST_ID = "import-page-ticker-options";

/** The three uploadable B3 exports, in the order they appear on the page. */
const UPLOADS: {
  kind: ImportKind;
  title: string;
  sheet: string;
  description: string;
  statusKey: keyof ImportStatus;
}[] = [
  {
    kind: "positions",
    title: "Resumo de Negociação",
    sheet: "Negociação - Resumo",
    description:
      "Posição e preço médio por ativo. É a base autoritativa sobre a qual as operações manuais se somam.",
    statusKey: "position_summary",
  },
  {
    kind: "transactions",
    title: "Histórico de Negociação",
    sheet: "Negociação",
    description:
      "Todas as compras e vendas, operação a operação. Base da série de evolução do patrimônio.",
    statusKey: "transactions",
  },
  {
    kind: "proventos",
    title: "Proventos Recebidos",
    sheet: "Proventos Recebidos",
    description:
      "Dividendos, JCP e rendimentos recebidos — usados no total de proventos e na apuração.",
    statusKey: "proventos",
  },
];

const ORIGIN_FILTERS: { value: TradeOrigin; label: string }[] = [
  { value: "manual", label: "Manuais" },
  { value: "import", label: "Importadas" },
  { value: "all", label: "Todas" },
];

export function ImportPage() {
  const importStatus = useImportStatus();
  const positions = usePositions();
  const clearSuperseded = useClearSuperseded();
  const queryClient = useQueryClient();
  const { notify } = useToast();

  const [originFilter, setOriginFilter] = useState<TradeOrigin>("manual");
  const trades = useTrades(originFilter);

  const manualCount = trades.data?.manual_count ?? 0;
  const latestManual = trades.data?.latest_manual_trade_date ?? null;

  // Autocomplete pool: held tickers + any ticker already seen in the list.
  const tickerOptions = useMemo(() => {
    const set = new Set<string>();
    positions.data?.positions.forEach((p) => set.add(p.ticker));
    trades.data?.trades.forEach((t) => set.add(t.ticker));
    return Array.from(set).sort();
  }, [positions.data, trades.data]);

  const handleClearSuperseded = () => {
    clearSuperseded.mutate(undefined, {
      onSuccess: (result) => {
        void queryClient.invalidateQueries({ queryKey: queryKeys.importStatus });
        notify(
          result.deleted > 0
            ? `${result.deleted} operação(ões) manual(is) superada(s) removida(s).`
            : "Nenhuma operação manual estava superada.",
          result.deleted > 0 ? "success" : "info",
        );
      },
    });
  };

  const rows = trades.data?.trades ?? [];

  return (
    <div className="space-y-10">
      <PageHeader
        title="Importar e operações manuais"
        description="Carregue seus extratos da B3 e registre operações manuais que complementam a última importação."
      />

      {/* ── B3 exports ─────────────────────────────────────────────────── */}
      <section className="space-y-4">
        <div>
          <h2 className="text-base font-semibold text-neutral-800 dark:text-neutral-100">
            Extratos da B3
          </h2>
          <p className="mt-0.5 text-sm text-neutral-500 dark:text-neutral-400">
            Baixe os relatórios no portal da B3 (formato{" "}
            <code className="font-mono">.xlsx</code>) e envie cada um abaixo.
            Reimportar substitui apenas os dados importados — suas operações
            manuais são sempre preservadas.
          </p>
        </div>

        {importStatus.isError && (
          <ErrorBanner
            title="Não foi possível carregar o status das importações"
            message={extractErrorMessage(importStatus.error)}
            onRetry={() => void importStatus.refetch()}
          />
        )}

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          {UPLOADS.map((upload) => (
            <ImportPageUploadCard
              key={upload.kind}
              kind={upload.kind}
              title={upload.title}
              sheet={upload.sheet}
              description={upload.description}
              status={importStatus.data?.[upload.statusKey]}
              statusLoading={importStatus.isLoading}
            />
          ))}
        </div>
      </section>

      {/* ── Manual trades ──────────────────────────────────────────────── */}
      <section className="space-y-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold text-neutral-800 dark:text-neutral-100">
              Operações manuais
            </h2>
            <p className="mt-0.5 max-w-2xl text-sm text-neutral-500 dark:text-neutral-400">
              Registre compras e vendas que os extratos ainda não cobrem. Elas
              se somam ao último resumo da B3 (a partir da data final dele) e
              são preservadas em reimportações.
            </p>
          </div>
          {manualCount > 0 && (
            <button
              type="button"
              onClick={handleClearSuperseded}
              disabled={clearSuperseded.isPending}
              title="Remove operações manuais já cobertas por um resumo da B3 mais recente, evitando dupla contagem."
              className="inline-flex items-center gap-2 rounded-lg border border-neutral-300 px-3 py-2 text-sm font-medium text-neutral-700 transition-colors hover:bg-neutral-100 disabled:cursor-not-allowed disabled:opacity-60 dark:border-neutral-700 dark:text-neutral-200 dark:hover:bg-neutral-800"
            >
              {clearSuperseded.isPending && (
                <LoadingSpinner className="h-4 w-4" />
              )}
              Limpar operações superadas
            </button>
          )}
        </div>

        {/* Staleness / reconciliation hint */}
        {manualCount > 0 && (
          <div className="flex items-start gap-3 rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:border-amber-800/70 dark:bg-amber-950/40 dark:text-amber-200">
            <span aria-hidden className="text-base leading-none">
              ⚠️
            </span>
            <p>
              Você tem{" "}
              <span className="font-semibold tabular-nums">{manualCount}</span>{" "}
              operação(ões) manual(is)
              {latestManual && (
                <>
                  {" "}
                  (a mais recente em{" "}
                  <span className="font-semibold tabular-nums">
                    {formatDate(latestManual)}
                  </span>
                  )
                </>
              )}
              . Assim que a B3 disponibilizar um resumo que já as inclua,
              reimporte o extrato para reconciliar e use{" "}
              <span className="font-medium">Limpar operações superadas</span>{" "}
              para evitar dupla contagem.
            </p>
          </div>
        )}

        <ImportPageTradeForm datalistId={TICKER_DATALIST_ID} />

        <Card
          title="Operações registradas"
          flush
          action={
            <div
              role="group"
              aria-label="Filtrar operações por origem"
              className="inline-flex rounded-lg border border-neutral-200 p-0.5 dark:border-neutral-700"
            >
              {ORIGIN_FILTERS.map((filter) => (
                <button
                  key={filter.value}
                  type="button"
                  aria-pressed={originFilter === filter.value}
                  onClick={() => setOriginFilter(filter.value)}
                  className={clsx(
                    "rounded-md px-2.5 py-1 text-xs font-medium transition-colors",
                    originFilter === filter.value
                      ? "bg-brand-600 text-white"
                      : "text-neutral-500 hover:text-neutral-800 dark:text-neutral-400 dark:hover:text-neutral-100",
                  )}
                >
                  {filter.label}
                </button>
              ))}
            </div>
          }
        >
          {trades.isLoading ? (
            <div className="p-6">
              <LoadingSpinner label="Carregando operações…" />
            </div>
          ) : trades.isError ? (
            <div className="p-4">
              <ErrorBanner
                message={extractErrorMessage(trades.error)}
                onRetry={() => void trades.refetch()}
              />
            </div>
          ) : rows.length === 0 ? (
            <div className="p-4">
              <EmptyState
                icon="🧾"
                title={
                  originFilter === "import"
                    ? "Nenhuma operação importada"
                    : originFilter === "all"
                      ? "Nenhuma operação registrada"
                      : "Nenhuma operação manual"
                }
                description={
                  originFilter === "import"
                    ? "Importe o Histórico de Negociação acima para ver suas operações da B3 aqui."
                    : "Adicione uma operação no formulário acima para complementar sua última importação."
                }
              />
            </div>
          ) : (
            <ImportPageTradesTable
              trades={rows}
              datalistId={TICKER_DATALIST_ID}
              showOrigin={originFilter !== "manual"}
            />
          )}
        </Card>
      </section>

      {/* Shared ticker autocomplete pool (always mounted for the add form). */}
      <datalist id={TICKER_DATALIST_ID}>
        {tickerOptions.map((t) => (
          <option key={t} value={t} />
        ))}
      </datalist>
    </div>
  );
}
