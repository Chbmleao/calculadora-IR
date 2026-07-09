import { Fragment, useState } from "react";
import type { FormEvent } from "react";
import clsx from "clsx";
import { useQueryClient } from "@tanstack/react-query";

import { extractErrorMessage } from "../api/client";
import { queryKeys, useDeleteTrade, useEditTrade } from "../api/hooks";
import type { Trade, TradeSide, TradeUpdate } from "../api/types";
import { formatBRL, formatDate } from "../lib/format";
import { useToast } from "../lib/toast";
import { LoadingSpinner } from "./LoadingSpinner";

const inputClass =
  "w-full rounded-lg border border-neutral-300 bg-white px-2.5 py-1.5 text-sm text-neutral-900 shadow-sm outline-none transition focus:border-brand-500 focus:ring-2 focus:ring-brand-500/30 dark:border-neutral-700 dark:bg-neutral-950 dark:text-neutral-100";
const labelClass =
  "mb-1 block text-xs font-medium text-neutral-600 dark:text-neutral-400";
const thClass =
  "px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-neutral-500 dark:text-neutral-400";
const tdClass = "px-3 py-2.5 align-middle";

function todayISO(): string {
  // Local (pt-BR) calendar date, not UTC — otherwise late-evening BR (UTC-3) rolls
  // to tomorrow and would accept a locally-future-dated trade.
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(
    d.getDate(),
  ).padStart(2, "0")}`;
}

function toNumber(raw: string): number {
  if (raw.trim() === "") return Number.NaN;
  return Number(raw.replace(",", "."));
}

function formatQty(value: number): string {
  return value.toLocaleString("pt-BR", { maximumFractionDigits: 8 });
}

interface ImportPageTradesTableProps {
  trades: Trade[];
  /** id of the shared `<datalist>` rendered by the page (edit inputs use it). */
  datalistId: string;
  /** Show an "Origem" column (when the view includes imported rows). */
  showOrigin: boolean;
}

/**
 * Manual trades list with inline edit + delete. Imported rows (`origin` !=
 * "manual") are rendered read-only — they can only be changed by re-importing.
 */
export function ImportPageTradesTable({
  trades,
  datalistId,
  showOrigin,
}: ImportPageTradesTableProps) {
  const editTrade = useEditTrade();
  const deleteTrade = useDeleteTrade();
  const queryClient = useQueryClient();
  const { notify } = useToast();

  const [editingId, setEditingId] = useState<number | null>(null);
  const [confirmingId, setConfirmingId] = useState<number | null>(null);

  const cols = 7 + (showOrigin ? 1 : 0) + 1;

  const handleSave = (tradeId: number, update: TradeUpdate) => {
    editTrade.mutate(
      { tradeId, update },
      {
        onSuccess: (trade) => {
          notify(`Operação ${trade.ticker} atualizada.`, "success");
          setEditingId(null);
        },
      },
    );
  };

  const handleDelete = (trade: Trade) => {
    deleteTrade.mutate(trade.id, {
      onSuccess: () => {
        // Deleting a manual row drops a transactions row — refresh the status.
        void queryClient.invalidateQueries({ queryKey: queryKeys.importStatus });
        notify(`Operação ${trade.ticker} excluída.`, "success");
        setConfirmingId(null);
      },
    });
  };

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[54rem] border-collapse text-sm">
        <thead>
          <tr className="border-b border-neutral-200 dark:border-neutral-800">
            <th className={thClass}>Data</th>
            <th className={thClass}>Ativo</th>
            <th className={thClass}>Tipo</th>
            <th className={clsx(thClass, "text-right")}>Qtd.</th>
            <th className={clsx(thClass, "text-right")}>Preço</th>
            <th className={clsx(thClass, "text-right")}>Total</th>
            <th className={thClass}>Instituição</th>
            {showOrigin && <th className={thClass}>Origem</th>}
            <th className={clsx(thClass, "text-right")}>Ações</th>
          </tr>
        </thead>
        <tbody>
          {trades.map((trade) => {
            const isManual = trade.origin === "manual";
            const isEditing = editingId === trade.id;
            const isConfirming = confirmingId === trade.id;
            return (
              <Fragment key={trade.id}>
                <tr
                  className={clsx(
                    "border-b border-neutral-100 dark:border-neutral-800/60",
                    isEditing && "bg-brand-50/60 dark:bg-brand-900/10",
                  )}
                >
                  <td className={clsx(tdClass, "whitespace-nowrap tabular-nums")}>
                    {formatDate(trade.trade_date)}
                  </td>
                  <td className={clsx(tdClass, "font-mono font-medium")}>
                    <span className="text-neutral-900 dark:text-neutral-100">
                      {trade.ticker}
                    </span>
                    {trade.note && (
                      <span
                        className="block max-w-[16rem] truncate font-sans text-xs text-neutral-400 dark:text-neutral-500"
                        title={trade.note}
                      >
                        {trade.note}
                      </span>
                    )}
                  </td>
                  <td className={tdClass}>
                    <SideBadge side={trade.side} />
                  </td>
                  <td
                    className={clsx(tdClass, "text-right tabular-nums")}
                  >
                    {formatQty(trade.quantity)}
                  </td>
                  <td className={clsx(tdClass, "text-right tabular-nums")}>
                    {formatBRL(trade.price)}
                  </td>
                  <td
                    className={clsx(
                      tdClass,
                      "text-right font-medium tabular-nums",
                    )}
                  >
                    {formatBRL(trade.value)}
                  </td>
                  <td
                    className={clsx(
                      tdClass,
                      "max-w-[12rem] truncate text-neutral-600 dark:text-neutral-300",
                    )}
                    title={trade.institution ?? undefined}
                  >
                    {trade.institution ?? "—"}
                  </td>
                  {showOrigin && (
                    <td className={tdClass}>
                      <OriginBadge origin={trade.origin} />
                    </td>
                  )}
                  <td className={clsx(tdClass, "text-right")}>
                    {!isManual ? (
                      <span className="text-xs text-neutral-400 dark:text-neutral-500">
                        somente leitura
                      </span>
                    ) : isConfirming ? (
                      <span className="inline-flex items-center gap-2">
                        <span className="text-xs text-neutral-500 dark:text-neutral-400">
                          Excluir?
                        </span>
                        <button
                          type="button"
                          onClick={() => handleDelete(trade)}
                          disabled={deleteTrade.isPending}
                          className="rounded-md bg-rose-600 px-2 py-1 text-xs font-medium text-white transition-colors hover:bg-rose-700 disabled:opacity-60"
                        >
                          Sim
                        </button>
                        <button
                          type="button"
                          onClick={() => setConfirmingId(null)}
                          className="rounded-md border border-neutral-300 px-2 py-1 text-xs font-medium text-neutral-600 transition-colors hover:bg-neutral-100 dark:border-neutral-700 dark:text-neutral-300 dark:hover:bg-neutral-800"
                        >
                          Não
                        </button>
                      </span>
                    ) : (
                      <span className="inline-flex items-center justify-end gap-1">
                        <button
                          type="button"
                          onClick={() => {
                            setConfirmingId(null);
                            setEditingId(isEditing ? null : trade.id);
                          }}
                          className="rounded-md border border-neutral-300 px-2 py-1 text-xs font-medium text-neutral-700 transition-colors hover:bg-neutral-100 dark:border-neutral-700 dark:text-neutral-200 dark:hover:bg-neutral-800"
                        >
                          {isEditing ? "Fechar" : "Editar"}
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            setEditingId(null);
                            setConfirmingId(trade.id);
                          }}
                          className="rounded-md border border-rose-300 px-2 py-1 text-xs font-medium text-rose-600 transition-colors hover:bg-rose-50 dark:border-rose-800 dark:text-rose-400 dark:hover:bg-rose-950/50"
                        >
                          Excluir
                        </button>
                      </span>
                    )}
                  </td>
                </tr>
                {isEditing && (
                  <TradeEditRow
                    trade={trade}
                    cols={cols}
                    datalistId={datalistId}
                    isPending={editTrade.isPending}
                    error={
                      editTrade.isError
                        ? extractErrorMessage(editTrade.error)
                        : null
                    }
                    onCancel={() => setEditingId(null)}
                    onSave={(update) => handleSave(trade.id, update)}
                  />
                )}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function SideBadge({ side }: { side: string }) {
  const isBuy = side === "buy";
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium",
        isBuy
          ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300"
          : "bg-rose-100 text-rose-700 dark:bg-rose-950 dark:text-rose-300",
      )}
    >
      <span aria-hidden>{isBuy ? "↑" : "↓"}</span>
      {isBuy ? "Compra" : "Venda"}
    </span>
  );
}

function OriginBadge({ origin }: { origin: string }) {
  const isManual = origin === "manual";
  return (
    <span
      className={clsx(
        "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium",
        isManual
          ? "bg-brand-100 text-brand-700 dark:bg-brand-900/40 dark:text-brand-300"
          : "bg-neutral-100 text-neutral-500 dark:bg-neutral-800 dark:text-neutral-400",
      )}
    >
      {isManual ? "Manual" : "Importada"}
    </span>
  );
}

interface TradeEditRowProps {
  trade: Trade;
  cols: number;
  datalistId: string;
  isPending: boolean;
  error: string | null;
  onCancel: () => void;
  onSave: (update: TradeUpdate) => void;
}

function TradeEditRow({
  trade,
  cols,
  datalistId,
  isPending,
  error,
  onCancel,
  onSave,
}: TradeEditRowProps) {
  const [ticker, setTicker] = useState(trade.ticker);
  const [tradeDate, setTradeDate] = useState(trade.trade_date);
  const [side, setSide] = useState<TradeSide>(
    trade.side === "sell" ? "sell" : "buy",
  );
  const [quantity, setQuantity] = useState(String(trade.quantity));
  const [price, setPrice] = useState(String(trade.price));
  const [institution, setInstitution] = useState(trade.institution ?? "");
  const [note, setNote] = useState(trade.note ?? "");
  const [localError, setLocalError] = useState<string | null>(null);

  const qtyNum = toNumber(quantity);
  const priceNum = toNumber(price);
  const total = qtyNum > 0 && priceNum > 0 ? qtyNum * priceNum : null;

  const message = localError ?? error;

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    setLocalError(null);

    const canonical = ticker.trim().toUpperCase();
    if (!canonical) return setLocalError("Informe o código do ativo.");
    if (!tradeDate) return setLocalError("Informe a data da operação.");
    if (tradeDate > todayISO())
      return setLocalError("A data da operação não pode ser futura.");
    if (!(qtyNum > 0)) return setLocalError("A quantidade deve ser maior que zero.");
    if (!(priceNum > 0)) return setLocalError("O preço deve ser maior que zero.");

    onSave({
      trade_date: tradeDate,
      ticker: canonical,
      side,
      quantity: qtyNum,
      price: priceNum,
      institution: institution.trim() ? institution.trim() : null,
      note: note.trim() ? note.trim() : null,
    });
  };

  return (
    <tr className="bg-brand-50/60 dark:bg-brand-900/10">
      <td colSpan={cols} className="px-3 py-4">
        <form onSubmit={handleSubmit} className="space-y-3" noValidate>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <div>
              <label className={labelClass}>Ativo</label>
              <input
                list={datalistId}
                value={ticker}
                onChange={(e) => setTicker(e.target.value.toUpperCase())}
                autoComplete="off"
                className={clsx(inputClass, "font-mono uppercase")}
              />
            </div>
            <div>
              <label className={labelClass}>Data</label>
              <input
                type="date"
                value={tradeDate}
                max={todayISO()}
                onChange={(e) => setTradeDate(e.target.value)}
                className={inputClass}
              />
            </div>
            <div>
              <span className={labelClass}>Tipo</span>
              <div className="grid grid-cols-2 gap-2">
                <button
                  type="button"
                  aria-pressed={side === "buy"}
                  onClick={() => setSide("buy")}
                  className={clsx(
                    "flex items-center justify-center gap-1 rounded-lg border px-2 py-1.5 text-sm font-medium transition-colors",
                    side === "buy"
                      ? "border-emerald-500 bg-emerald-50 text-emerald-700 dark:border-emerald-500 dark:bg-emerald-950/60 dark:text-emerald-300"
                      : "border-neutral-300 text-neutral-500 hover:bg-neutral-50 dark:border-neutral-700 dark:text-neutral-400 dark:hover:bg-neutral-800",
                  )}
                >
                  <span aria-hidden>↑</span>Compra
                </button>
                <button
                  type="button"
                  aria-pressed={side === "sell"}
                  onClick={() => setSide("sell")}
                  className={clsx(
                    "flex items-center justify-center gap-1 rounded-lg border px-2 py-1.5 text-sm font-medium transition-colors",
                    side === "sell"
                      ? "border-rose-500 bg-rose-50 text-rose-700 dark:border-rose-500 dark:bg-rose-950/60 dark:text-rose-300"
                      : "border-neutral-300 text-neutral-500 hover:bg-neutral-50 dark:border-neutral-700 dark:text-neutral-400 dark:hover:bg-neutral-800",
                  )}
                >
                  <span aria-hidden>↓</span>Venda
                </button>
              </div>
            </div>
            <div>
              <label className={labelClass}>Quantidade</label>
              <input
                type="text"
                inputMode="decimal"
                autoComplete="off"
                value={quantity}
                onChange={(e) => setQuantity(e.target.value)}
                className={clsx(inputClass, "tabular-nums")}
              />
            </div>
            <div>
              <label className={labelClass}>Preço unitário</label>
              <input
                type="text"
                inputMode="decimal"
                autoComplete="off"
                value={price}
                onChange={(e) => setPrice(e.target.value)}
                className={clsx(inputClass, "tabular-nums")}
              />
            </div>
            <div>
              <label className={labelClass}>Instituição</label>
              <input
                value={institution}
                onChange={(e) => setInstitution(e.target.value)}
                className={inputClass}
              />
            </div>
            <div className="sm:col-span-2">
              <label className={labelClass}>Observação</label>
              <input
                value={note}
                onChange={(e) => setNote(e.target.value)}
                className={inputClass}
              />
            </div>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-sm text-neutral-500 dark:text-neutral-400">
              Total:{" "}
              <span className="font-semibold tabular-nums text-neutral-800 dark:text-neutral-100">
                {total != null ? formatBRL(total) : "—"}
              </span>
            </p>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={onCancel}
                className="rounded-lg border border-neutral-300 px-3 py-1.5 text-sm font-medium text-neutral-600 transition-colors hover:bg-neutral-100 dark:border-neutral-700 dark:text-neutral-300 dark:hover:bg-neutral-800"
              >
                Cancelar
              </button>
              <button
                type="submit"
                disabled={isPending}
                className="inline-flex items-center gap-2 rounded-lg bg-brand-600 px-4 py-1.5 text-sm font-medium text-white shadow-sm transition-colors hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {isPending && <LoadingSpinner className="h-4 w-4 border-white" />}
                Salvar
              </button>
            </div>
          </div>

          {message && (
            <p
              role="alert"
              className="rounded-lg border border-rose-300 bg-rose-50 px-3 py-2 text-sm text-rose-700 dark:border-rose-800 dark:bg-rose-950/50 dark:text-rose-300"
            >
              {message}
            </p>
          )}
        </form>
      </td>
    </tr>
  );
}
