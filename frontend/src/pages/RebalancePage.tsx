import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import clsx from "clsx";

import { extractErrorMessage } from "../api/client";
import {
  usePositions,
  useRebalance,
  useSaveTargets,
  useTargets,
} from "../api/hooks";
import type { TargetInput, TargetsUpdate } from "../api/types";
import { Card } from "../components/Card";
import { EmptyState } from "../components/EmptyState";
import { ErrorBanner } from "../components/ErrorBanner";
import { LoadingSpinner } from "../components/LoadingSpinner";
import { PageHeader } from "../components/PageHeader";
import {
  RebalancePageCurrentVsTargetChart,
  type CurrentVsTargetDatum,
} from "../components/RebalancePageCurrentVsTargetChart";
import { StatTile } from "../components/StatTile";
import { formatBRL, formatPct } from "../lib/format";
import { useToast } from "../lib/toast";

type View = "class" | "ticker";
type Draft = Record<string, string>;

/** Parse a target-percent input (accepts `,` or `.` decimals). */
function toNumber(value: string | undefined): number {
  if (!value || !value.trim()) return 0;
  const n = Number(value.replace(",", "."));
  return Number.isFinite(n) ? n : 0;
}

/** Parse a pt-BR currency field ("1.234,56" → 1234.56); clamps to ≥ 0. */
function parseContribution(raw: string): number {
  const cleaned = raw.replace(/[^\d.,]/g, "");
  if (!cleaned) return 0;
  const normalized = cleaned.replace(/\./g, "").replace(",", ".");
  const n = Number(normalized);
  return Number.isFinite(n) && n >= 0 ? n : 0;
}

/**
 * Diverging mini-bar for allocation drift: red to the right when overweight
 * (current > target), green to the left when underweight. Magnitude is scaled
 * against the largest drift in the table.
 */
function DriftBar({ value, maxAbs }: { value: number; maxAbs: number }) {
  const over = value > 0.005;
  const under = value < -0.005;
  const widthPct = (Math.min(Math.abs(value), maxAbs) / maxAbs) * 50;

  return (
    <div className="flex items-center gap-2">
      <div className="relative h-2 min-w-[56px] flex-1 rounded-full bg-neutral-100 dark:bg-neutral-800">
        <span className="absolute left-1/2 top-0 h-full w-px -translate-x-1/2 bg-neutral-300 dark:bg-neutral-600" />
        {over && (
          <span
            className="absolute left-1/2 top-0 h-full rounded-full bg-rose-500 dark:bg-rose-400"
            style={{ width: `${widthPct}%` }}
          />
        )}
        {under && (
          <span
            className="absolute top-0 h-full rounded-full bg-emerald-500 dark:bg-emerald-400"
            style={{ right: "50%", width: `${widthPct}%` }}
          />
        )}
      </div>
      <span
        className={clsx(
          "w-16 shrink-0 text-right text-xs tabular-nums",
          over && "text-rose-600 dark:text-rose-400",
          under && "text-emerald-600 dark:text-emerald-400",
          !over && !under && "text-neutral-400 dark:text-neutral-500",
        )}
      >
        {formatPct(value, { signed: true })}
      </span>
    </div>
  );
}

/** Target allocation editor + rebalancing / buy-suggestion plan (task 11). */
export function RebalancePage() {
  const positions = usePositions();
  const targets = useTargets();
  const saveTargets = useSaveTargets();
  const { notify } = useToast();

  const [view, setView] = useState<View>("class");
  const [classKeys, setClassKeys] = useState<string[]>([]);
  const [tickerKeys, setTickerKeys] = useState<string[]>([]);
  const [classDraft, setClassDraft] = useState<Draft>({});
  const [tickerDraft, setTickerDraft] = useState<Draft>({});
  const [newKey, setNewKey] = useState("");

  const [contributionInput, setContributionInput] = useState("");
  const [contribution, setContribution] = useState(0);

  const initialized = useRef(false);

  // Debounce the contribution field so the rebalance query only refetches once
  // the investor pauses typing.
  useEffect(() => {
    const handle = window.setTimeout(
      () => setContribution(parseContribution(contributionInput)),
      350,
    );
    return () => window.clearTimeout(handle);
  }, [contributionInput]);

  const rebalance = useRebalance(contribution);

  // Seed the editable drafts from saved targets, ensuring every held class /
  // ticker appears as a row (so a fresh portfolio can define targets too).
  const seedDrafts = useCallback(() => {
    const t = targets.data;
    const p = positions.data;
    if (!t || !p) return;

    const classOrder: string[] = [];
    const classVals: Draft = {};
    for (const c of p.allocation_by_class) {
      if (!(c.asset_class in classVals)) {
        classOrder.push(c.asset_class);
        classVals[c.asset_class] = "";
      }
    }
    for (const item of t.class_targets) {
      if (!(item.key in classVals)) classOrder.push(item.key);
      classVals[item.key] = String(item.target_pct);
    }

    const tickerOrder: string[] = [];
    const tickerVals: Draft = {};
    for (const pos of p.positions) {
      if (!(pos.ticker in tickerVals)) {
        tickerOrder.push(pos.ticker);
        tickerVals[pos.ticker] = "";
      }
    }
    for (const item of t.ticker_targets) {
      if (!(item.key in tickerVals)) tickerOrder.push(item.key);
      tickerVals[item.key] = String(item.target_pct);
    }

    setClassKeys(classOrder);
    setClassDraft(classVals);
    setTickerKeys(tickerOrder);
    setTickerDraft(tickerVals);
  }, [targets.data, positions.data]);

  useEffect(() => {
    if (initialized.current) return;
    if (!targets.data || !positions.data) return;
    seedDrafts();
    setView(
      targets.data.class_targets.length === 0 &&
        targets.data.ticker_targets.length > 0
        ? "ticker"
        : "class",
    );
    initialized.current = true;
  }, [targets.data, positions.data, seedDrafts]);

  const activeKeys = view === "class" ? classKeys : tickerKeys;
  const activeDraft = view === "class" ? classDraft : tickerDraft;

  const currentByKey = useMemo(() => {
    const map: Record<string, number> = {};
    const p = positions.data;
    if (!p) return map;
    if (view === "class") {
      for (const c of p.allocation_by_class) map[c.asset_class] = c.weight_pct;
    } else {
      for (const pos of p.positions) map[pos.ticker] = pos.weight_pct;
    }
    return map;
  }, [positions.data, view]);

  const runningTotal = useMemo(
    () => activeKeys.reduce((sum, key) => sum + toNumber(activeDraft[key]), 0),
    [activeKeys, activeDraft],
  );
  const balanced = Math.abs(runningTotal - 100) < 0.01;
  const remaining = 100 - runningTotal;

  const updateDraft = (key: string, value: string) => {
    const setter = view === "class" ? setClassDraft : setTickerDraft;
    setter((prev) => ({ ...prev, [key]: value }));
  };

  const removeKey = (key: string) => {
    if (view === "class") {
      setClassKeys((prev) => prev.filter((k) => k !== key));
      setClassDraft((prev) => {
        const next = { ...prev };
        delete next[key];
        return next;
      });
    } else {
      setTickerKeys((prev) => prev.filter((k) => k !== key));
      setTickerDraft((prev) => {
        const next = { ...prev };
        delete next[key];
        return next;
      });
    }
  };

  const addKey = () => {
    const raw = newKey.trim();
    if (!raw) return;
    const key = view === "ticker" ? raw.toUpperCase() : raw;
    if (activeKeys.includes(key)) {
      notify(`"${key}" já está na tabela.`, "info");
      return;
    }
    if (view === "class") {
      setClassKeys((prev) => [...prev, key]);
      setClassDraft((prev) => ({ ...prev, [key]: "" }));
    } else {
      setTickerKeys((prev) => [...prev, key]);
      setTickerDraft((prev) => ({ ...prev, [key]: "" }));
    }
    setNewKey("");
  };

  const handleSave = () => {
    const build = (keys: string[], draft: Draft): TargetInput[] =>
      keys
        .map((key) => ({ key, target_pct: toNumber(draft[key]) }))
        .filter((row) => row.target_pct > 0);

    const payload: TargetsUpdate = {
      class_targets: build(classKeys, classDraft),
      ticker_targets: build(tickerKeys, tickerDraft),
    };

    saveTargets.mutate(payload, {
      onSuccess: () => notify("Metas de alocação salvas.", "success"),
      // Errors are surfaced globally by the queryClient MutationCache.
    });
  };

  // ── Page-level states ────────────────────────────────────────────────────
  const ready = Boolean(positions.data && targets.data);
  const hasPositions = (positions.data?.positions.length ?? 0) > 0;

  const rows = rebalance.data?.rows ?? [];
  const hasAnyTarget = rows.some((row) => row.target_pct > 0);

  const chartData: CurrentVsTargetDatum[] = useMemo(
    () =>
      rows
        .filter((row) => row.target_pct > 0 || row.current_pct > 0)
        .map((row) => ({
          key: row.key,
          current: row.current_pct,
          target: row.target_pct,
        }))
        .sort((a, b) => b.target - a.target || b.current - a.current),
    [rows],
  );

  const sortedRows = useMemo(
    () =>
      [...rows].sort(
        (a, b) =>
          a.current_pct - a.target_pct - (b.current_pct - b.target_pct),
      ),
    [rows],
  );

  const maxAbsDrift = useMemo(
    () =>
      Math.max(
        1,
        ...rows.map((row) => Math.abs(row.current_pct - row.target_pct)),
      ),
    [rows],
  );

  const totalBuy = useMemo(
    () => rows.reduce((sum, row) => sum + row.suggested_buy_amount, 0),
    [rows],
  );

  const warnings = rebalance.data?.warnings ?? [];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Rebalanceamento"
        description="Defina os pesos-alvo, informe um aporte e veja o que comprar para se aproximar da sua meta."
      />

      {!ready && (positions.isLoading || targets.isLoading) && (
        <Card>
          <LoadingSpinner label="Carregando carteira e metas…" />
        </Card>
      )}

      {positions.isError && (
        <ErrorBanner
          message={extractErrorMessage(positions.error)}
          onRetry={() => void positions.refetch()}
        />
      )}
      {targets.isError && (
        <ErrorBanner
          message={extractErrorMessage(targets.error)}
          onRetry={() => void targets.refetch()}
        />
      )}

      {ready && !hasPositions && (
        <EmptyState
          icon="⚖️"
          title="Nenhuma posição importada"
          description="Importe o resumo de negociação da B3 para definir metas de alocação e receber sugestões de compra."
          action={
            <Link
              to="/import"
              className="inline-flex items-center gap-2 rounded-lg bg-brand-600 px-3 py-2 text-sm font-medium text-white shadow-sm transition-colors hover:bg-brand-700"
            >
              Importar dados
            </Link>
          }
        />
      )}

      {ready && hasPositions && (
        <>
          {/* ── Targets editor ─────────────────────────────────────────── */}
          <Card
            title="Metas de alocação"
            action={
              <div className="inline-flex rounded-lg border border-neutral-200 p-0.5 dark:border-neutral-700">
                {(["class", "ticker"] as const).map((option) => (
                  <button
                    key={option}
                    type="button"
                    onClick={() => setView(option)}
                    className={clsx(
                      "rounded-md px-3 py-1 text-xs font-medium transition-colors",
                      view === option
                        ? "bg-brand-600 text-white"
                        : "text-neutral-600 hover:bg-neutral-100 dark:text-neutral-300 dark:hover:bg-neutral-800",
                    )}
                  >
                    {option === "class" ? "Por classe" : "Por ativo"}
                  </button>
                ))}
              </div>
            }
          >
            <div className="overflow-x-auto">
              <table className="w-full min-w-[420px] text-sm">
                <thead>
                  <tr className="border-b border-neutral-200 text-left text-xs uppercase tracking-wide text-neutral-500 dark:border-neutral-800 dark:text-neutral-400">
                    <th className="py-2 pr-3 font-medium">
                      {view === "class" ? "Classe" : "Ativo"}
                    </th>
                    <th className="px-3 py-2 text-right font-medium">Atual</th>
                    <th className="px-3 py-2 text-right font-medium">Meta %</th>
                    <th className="py-2 pl-3" aria-label="Ações" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-neutral-100 dark:divide-neutral-800">
                  {activeKeys.length === 0 && (
                    <tr>
                      <td
                        colSpan={4}
                        className="py-6 text-center text-sm text-neutral-500 dark:text-neutral-400"
                      >
                        Nenhuma linha. Adicione uma{" "}
                        {view === "class" ? "classe" : "ativo"} abaixo.
                      </td>
                    </tr>
                  )}
                  {activeKeys.map((key) => (
                    <tr key={key}>
                      <td className="py-2 pr-3 font-medium text-neutral-800 dark:text-neutral-100">
                        {key}
                      </td>
                      <td className="px-3 py-2 text-right tabular-nums text-neutral-500 dark:text-neutral-400">
                        {formatPct(currentByKey[key] ?? 0)}
                      </td>
                      <td className="px-3 py-2 text-right">
                        <div className="inline-flex items-center gap-1">
                          <input
                            type="text"
                            inputMode="decimal"
                            value={activeDraft[key] ?? ""}
                            onChange={(e) => updateDraft(key, e.target.value)}
                            placeholder="0"
                            aria-label={`Meta para ${key}`}
                            className="w-20 rounded-md border border-neutral-300 bg-white px-2 py-1 text-right tabular-nums text-neutral-900 focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500 dark:border-neutral-700 dark:bg-neutral-950 dark:text-neutral-100"
                          />
                          <span className="text-neutral-400">%</span>
                        </div>
                      </td>
                      <td className="py-2 pl-3 text-right">
                        <button
                          type="button"
                          onClick={() => removeKey(key)}
                          aria-label={`Remover ${key}`}
                          className="rounded-md px-2 py-1 text-neutral-400 transition-colors hover:bg-neutral-100 hover:text-rose-500 dark:hover:bg-neutral-800"
                        >
                          ×
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr className="border-t border-neutral-200 dark:border-neutral-800">
                    <td className="py-2 pr-3 text-xs font-medium uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
                      Soma
                    </td>
                    <td />
                    <td className="px-3 py-2 text-right">
                      <span
                        className={clsx(
                          "inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-sm font-semibold tabular-nums",
                          balanced
                            ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300"
                            : "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300",
                        )}
                      >
                        {balanced ? "✓" : "⚠"} {formatPct(runningTotal)}
                      </span>
                    </td>
                    <td />
                  </tr>
                </tfoot>
              </table>
            </div>

            {!balanced && (
              <p className="mt-3 text-xs text-amber-600 dark:text-amber-400">
                A soma das metas é {formatPct(runningTotal)} —{" "}
                {remaining > 0 ? "faltam" : "excede em"}{" "}
                {formatPct(Math.abs(remaining))} para 100%. As sugestões ainda
                são calculadas.
              </p>
            )}

            <form
              onSubmit={(e) => {
                e.preventDefault();
                addKey();
              }}
              className="mt-4 flex flex-wrap items-center gap-2"
            >
              <input
                type="text"
                value={newKey}
                onChange={(e) => setNewKey(e.target.value)}
                placeholder={
                  view === "class"
                    ? "Adicionar classe (ex.: FII)"
                    : "Adicionar ativo (ex.: PETR4)"
                }
                aria-label="Nova chave de meta"
                className="min-w-[180px] flex-1 rounded-lg border border-neutral-300 bg-white px-3 py-2 text-sm text-neutral-900 focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500 dark:border-neutral-700 dark:bg-neutral-950 dark:text-neutral-100"
              />
              <button
                type="submit"
                className="rounded-lg border border-neutral-300 px-3 py-2 text-sm font-medium text-neutral-700 transition-colors hover:bg-neutral-100 dark:border-neutral-700 dark:text-neutral-200 dark:hover:bg-neutral-800"
              >
                Adicionar
              </button>
            </form>

            <div className="mt-4 flex flex-wrap items-center justify-end gap-2 border-t border-neutral-200 pt-4 dark:border-neutral-800">
              <button
                type="button"
                onClick={seedDrafts}
                disabled={saveTargets.isPending}
                className="rounded-lg border border-neutral-300 px-3 py-2 text-sm font-medium text-neutral-700 transition-colors hover:bg-neutral-100 disabled:opacity-50 dark:border-neutral-700 dark:text-neutral-200 dark:hover:bg-neutral-800"
              >
                Reverter
              </button>
              <button
                type="button"
                onClick={handleSave}
                disabled={saveTargets.isPending}
                className="inline-flex items-center gap-2 rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white shadow-sm transition-colors hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {saveTargets.isPending && (
                  <LoadingSpinner className="h-4 w-4 border-white" />
                )}
                Salvar metas
              </button>
            </div>
          </Card>

          {/* ── Contribution ("Aporte") ─────────────────────────────────── */}
          <Card title="Aporte">
            <label
              htmlFor="rebalance-aporte"
              className="block text-sm text-neutral-600 dark:text-neutral-300"
            >
              Quanto você quer investir agora? As sugestões são apenas de
              compra — nada é vendido.
            </label>
            <div className="mt-2 flex items-center gap-2">
              <span className="text-neutral-500 dark:text-neutral-400">R$</span>
              <input
                id="rebalance-aporte"
                type="text"
                inputMode="decimal"
                value={contributionInput}
                onChange={(e) => setContributionInput(e.target.value)}
                placeholder="0,00"
                className="w-40 rounded-lg border border-neutral-300 bg-white px-3 py-2 text-right tabular-nums text-neutral-900 focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500 dark:border-neutral-700 dark:bg-neutral-950 dark:text-neutral-100"
              />
            </div>
          </Card>

          {/* ── Summary tiles ───────────────────────────────────────────── */}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatTile
              label="Valor da carteira"
              value={
                rebalance.data
                  ? formatBRL(rebalance.data.total_market_value)
                  : "—"
              }
            />
            <StatTile
              label="Aporte"
              value={rebalance.data ? formatBRL(rebalance.data.contribution) : "—"}
            />
            <StatTile
              label="Total a comprar"
              value={rebalance.data ? formatBRL(totalBuy) : "—"}
              hint={rebalance.data ? "Somatório das sugestões" : undefined}
            />
            <StatTile
              label="Sobra em caixa"
              value={
                rebalance.data ? formatBRL(rebalance.data.leftover_cash) : "—"
              }
              hint={rebalance.data ? "Não alocado (preço indivisível)" : undefined}
            />
          </div>

          {warnings.length > 0 && (
            <div className="rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:border-amber-800 dark:bg-amber-950/50 dark:text-amber-200">
              <ul className="list-disc space-y-0.5 pl-5">
                {warnings.map((warning, i) => (
                  <li key={i}>{warning}</li>
                ))}
              </ul>
            </div>
          )}

          {/* ── Rebalance error / loading / plan ─────────────────────────── */}
          {rebalance.isError && (
            <ErrorBanner
              title="Não foi possível calcular o rebalanceamento"
              message={extractErrorMessage(rebalance.error)}
              onRetry={() => void rebalance.refetch()}
            />
          )}

          {!rebalance.isError && rebalance.isLoading && (
            <Card>
              <LoadingSpinner label="Calculando plano de rebalanceamento…" />
            </Card>
          )}

          {!rebalance.isError && !rebalance.isLoading && !hasAnyTarget && (
            <EmptyState
              icon="🎯"
              title="Defina sua alocação-alvo"
              description="Informe uma porcentagem-alvo por classe ou ativo acima e salve para ver o comparativo e as sugestões de compra."
            />
          )}

          {!rebalance.isError && !rebalance.isLoading && hasAnyTarget && (
            <>
              <Card title="Atual vs meta">
                <RebalancePageCurrentVsTargetChart data={chartData} />
              </Card>

              <Card title="Plano de compras" flush>
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[720px] text-sm">
                    <thead>
                      <tr className="border-b border-neutral-200 text-left text-xs uppercase tracking-wide text-neutral-500 dark:border-neutral-800 dark:text-neutral-400">
                        <th className="px-4 py-3 font-medium">Ativo</th>
                        <th className="px-4 py-3 text-right font-medium">
                          Atual %
                        </th>
                        <th className="px-4 py-3 text-right font-medium">
                          Meta %
                        </th>
                        <th className="min-w-[160px] px-4 py-3 font-medium">
                          Drift
                        </th>
                        <th className="px-4 py-3 text-right font-medium">
                          Valor atual
                        </th>
                        <th className="px-4 py-3 text-right font-medium">
                          Comprar
                        </th>
                        <th className="px-4 py-3 text-right font-medium">Qtd.</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-neutral-100 dark:divide-neutral-800">
                      {sortedRows.map((row) => {
                        const drift = row.current_pct - row.target_pct;
                        return (
                          <tr
                            key={`${row.kind}:${row.key}`}
                            className="hover:bg-neutral-50 dark:hover:bg-neutral-800/40"
                          >
                            <td className="px-4 py-3 font-medium text-neutral-800 dark:text-neutral-100">
                              {row.key}
                            </td>
                            <td className="px-4 py-3 text-right tabular-nums text-neutral-600 dark:text-neutral-300">
                              {formatPct(row.current_pct)}
                            </td>
                            <td className="px-4 py-3 text-right tabular-nums text-neutral-600 dark:text-neutral-300">
                              {formatPct(row.target_pct)}
                            </td>
                            <td className="px-4 py-3">
                              <DriftBar value={drift} maxAbs={maxAbsDrift} />
                            </td>
                            <td className="px-4 py-3 text-right tabular-nums text-neutral-600 dark:text-neutral-300">
                              {formatBRL(row.current_value)}
                            </td>
                            <td
                              className={clsx(
                                "px-4 py-3 text-right font-medium tabular-nums",
                                row.suggested_buy_amount > 0
                                  ? "text-emerald-600 dark:text-emerald-400"
                                  : "text-neutral-400 dark:text-neutral-500",
                              )}
                            >
                              {row.suggested_buy_amount > 0
                                ? formatBRL(row.suggested_buy_amount)
                                : "—"}
                            </td>
                            <td className="px-4 py-3 text-right tabular-nums text-neutral-600 dark:text-neutral-300">
                              {row.suggested_buy_qty != null
                                ? row.suggested_buy_qty
                                : "—"}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
                <div className="flex flex-wrap items-center justify-between gap-2 border-t border-neutral-200 px-4 py-3 text-sm dark:border-neutral-800">
                  <span className="flex items-center gap-4 text-xs text-neutral-500 dark:text-neutral-400">
                    <span className="inline-flex items-center gap-1.5">
                      <span className="inline-block h-2.5 w-2.5 rounded-sm bg-rose-500 dark:bg-rose-400" />
                      Acima da meta
                    </span>
                    <span className="inline-flex items-center gap-1.5">
                      <span className="inline-block h-2.5 w-2.5 rounded-sm bg-emerald-500 dark:bg-emerald-400" />
                      Abaixo da meta
                    </span>
                  </span>
                  <span className="tabular-nums text-neutral-600 dark:text-neutral-300">
                    Sobra em caixa:{" "}
                    <span className="font-semibold">
                      {formatBRL(rebalance.data?.leftover_cash ?? 0)}
                    </span>
                  </span>
                </div>
              </Card>
            </>
          )}
        </>
      )}
    </div>
  );
}
