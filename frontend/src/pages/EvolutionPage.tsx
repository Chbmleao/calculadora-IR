import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import clsx from "clsx";

import { extractErrorMessage } from "../api/client";
import { useEvolution } from "../api/hooks";
import type { EvolutionGranularity } from "../api/types";
import { Card } from "../components/Card";
import { EmptyState } from "../components/EmptyState";
import { ErrorBanner } from "../components/ErrorBanner";
import {
  EvolutionPagePatrimonyChart,
  type Period,
} from "../components/EvolutionPagePatrimonyChart";
import { LoadingSpinner } from "../components/LoadingSpinner";
import { PageHeader } from "../components/PageHeader";
import { formatBRL, formatDate, formatPct } from "../lib/format";

const MS_PER_DAY = 86_400_000;

/** A signed headline metric. Colors the value by sign; `sign = null` → neutral. */
function MetricTile({
  label,
  value,
  sign,
  info,
}: {
  label: string;
  value: string;
  sign: number | null;
  info?: string;
}) {
  const valueClass =
    sign == null || sign === 0
      ? "text-neutral-900 dark:text-neutral-50"
      : sign > 0
        ? "text-emerald-600 dark:text-emerald-400"
        : "text-rose-600 dark:text-rose-400";
  return (
    <Card>
      <div className="flex items-center gap-1">
        <p className="text-xs font-medium uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
          {label}
        </p>
        {info && (
          <span
            tabIndex={0}
            role="note"
            aria-label={info}
            title={info}
            className="cursor-help text-neutral-400 transition-colors hover:text-neutral-600 dark:text-neutral-500 dark:hover:text-neutral-300"
          >
            ⓘ
          </span>
        )}
      </div>
      <p className={clsx("mt-1 text-2xl font-semibold", valueClass)}>{value}</p>
    </Card>
  );
}

/** Compact segmented toggle used for the period + granularity controls. */
function SegmentedControl<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: { value: T; label: string }[];
  onChange: (value: T) => void;
}) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-xs font-medium uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
        {label}
      </span>
      <div
        role="group"
        aria-label={label}
        className="inline-flex rounded-lg border border-neutral-200 bg-neutral-50 p-0.5 dark:border-neutral-800 dark:bg-neutral-950"
      >
        {options.map((option) => {
          const active = option.value === value;
          return (
            <button
              key={option.value}
              type="button"
              aria-pressed={active}
              onClick={() => onChange(option.value)}
              className={clsx(
                "rounded-md px-2.5 py-1 text-xs font-medium transition-colors",
                active
                  ? "bg-white text-neutral-900 shadow-sm dark:bg-neutral-800 dark:text-neutral-50"
                  : "text-neutral-500 hover:text-neutral-800 dark:text-neutral-400 dark:hover:text-neutral-100",
              )}
            >
              {option.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}

const PERIOD_OPTIONS: { value: Period; label: string }[] = [
  { value: "ytd", label: "No ano" },
  { value: "1y", label: "1 ano" },
  { value: "all", label: "Tudo" },
];

const GRANULARITY_OPTIONS: { value: EvolutionGranularity; label: string }[] = [
  { value: "daily", label: "Diário" },
  { value: "weekly", label: "Semanal" },
  { value: "monthly", label: "Mensal" },
];

/**
 * Evolution — patrimony over time and true return (task 10). Charts the equity
 * curve against cumulative contributions (gap = market gain/loss), surfaces the
 * headline return metrics, and lets the reader retune period + granularity.
 *
 * Note: `useEvolution()` (the typed hook) takes no query params, so the
 * period/granularity controls resample the full series client-side rather than
 * refetching with `granularity`/`from`/`to`.
 */
export function EvolutionPage() {
  const { data, isLoading, isError, error, refetch, isFetching } = useEvolution();

  const [period, setPeriod] = useState<Period>("all");
  const [granularity, setGranularity] = useState<EvolutionGranularity>("monthly");
  const didInitGranularity = useRef(false);

  // Prefer a coarse granularity for long histories, then let the user drill in.
  useEffect(() => {
    if (didInitGranularity.current || !data || data.points.length === 0) return;
    didInitGranularity.current = true;
    const first = data.points[0].date;
    const last = data.points[data.points.length - 1].date;
    const spanDays = (Date.parse(last) - Date.parse(first)) / MS_PER_DAY;
    setGranularity(spanDays > 550 ? "monthly" : spanDays > 120 ? "weekly" : "daily");
  }, [data]);

  const metrics = data?.metrics;
  const twr = metrics?.twr ?? null;
  const simpleReturn = metrics?.simple_return ?? null;
  const xirr = metrics?.xirr ?? null;
  const absoluteGain = metrics?.absolute_gain ?? null;
  const hasPoints = (data?.points.length ?? 0) > 0;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Evolução"
        description="Patrimônio ao longo do tempo e rentabilidade real — o quanto veio de aportes e o quanto veio do mercado."
        actions={
          data?.as_of ? (
            <span className="inline-flex items-center gap-1.5 rounded-full border border-neutral-200 bg-neutral-50 px-3 py-1 text-xs font-medium text-neutral-600 dark:border-neutral-800 dark:bg-neutral-900 dark:text-neutral-300">
              <span
                aria-hidden
                className="inline-block h-1.5 w-1.5 rounded-full bg-emerald-500"
              />
              Atualizado em {formatDate(data.as_of)}
            </span>
          ) : undefined
        }
      />

      {isLoading && (
        <Card>
          <div className="flex h-[22rem] items-center justify-center">
            <LoadingSpinner label="Carregando evolução…" />
          </div>
        </Card>
      )}

      {isError && (
        <ErrorBanner
          message={extractErrorMessage(error)}
          onRetry={() => void refetch()}
        />
      )}

      {!isLoading && !isError && data && !hasPoints && (
        <EmptyState
          icon="📈"
          title="Sem histórico ainda"
          description="Importe seu histórico de negociação para reconstruir a curva de patrimônio e separar aportes de ganhos de mercado."
          action={
            <Link
              to="/import"
              className="inline-flex items-center gap-1 rounded-lg bg-neutral-900 px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-neutral-700 dark:bg-neutral-100 dark:text-neutral-900 dark:hover:bg-neutral-300"
            >
              Importar histórico
            </Link>
          }
        />
      )}

      {!isLoading && !isError && data && hasPoints && (
        <>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <MetricTile
              label="Rentabilidade (TWR)"
              value={formatPct(twr == null ? null : twr * 100, { signed: true })}
              sign={twr}
              info="Retorno que exclui o efeito de aportes e resgates (time-weighted return)."
            />
            <MetricTile
              label="Retorno simples"
              value={formatPct(simpleReturn == null ? null : simpleReturn * 100, {
                signed: true,
              })}
              sign={simpleReturn}
              info="Ganho total sobre o valor aportado, sem ajustar o momento dos aportes."
            />
            <MetricTile
              label="Ganho absoluto"
              value={formatBRL(absoluteGain)}
              sign={absoluteGain}
              info="Patrimônio atual menos o total aportado, em reais."
            />
            {xirr != null && (
              <MetricTile
                label="Rentabilidade anual (XIRR)"
                value={formatPct(xirr * 100, { signed: true })}
                sign={xirr}
                info="Taxa interna de retorno anualizada, considerando as datas dos aportes."
              />
            )}
          </div>

          <div className="space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h2 className="text-sm font-semibold text-neutral-700 dark:text-neutral-200">
                Evolução do patrimônio
              </h2>
              <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
                <SegmentedControl
                  label="Período"
                  value={period}
                  options={PERIOD_OPTIONS}
                  onChange={setPeriod}
                />
                <SegmentedControl
                  label="Frequência"
                  value={granularity}
                  options={GRANULARITY_OPTIONS}
                  onChange={setGranularity}
                />
              </div>
            </div>

            <Card>
              <div
                className={clsx(
                  "transition-opacity",
                  isFetching && "opacity-60",
                )}
              >
                <EvolutionPagePatrimonyChart
                  points={data.points}
                  granularity={granularity}
                  period={period}
                  asOf={data.as_of}
                />
              </div>
            </Card>
          </div>
        </>
      )}
    </div>
  );
}
