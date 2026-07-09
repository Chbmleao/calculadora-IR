import { useState } from "react";
import type { FormEvent } from "react";
import clsx from "clsx";
import { useQueryClient } from "@tanstack/react-query";

import { extractErrorMessage } from "../api/client";
import { queryKeys, useAddTrade } from "../api/hooks";
import type { TradeInput, TradeSide } from "../api/types";
import { formatBRL } from "../lib/format";
import { useToast } from "../lib/toast";
import { Card } from "./Card";
import { LoadingSpinner } from "./LoadingSpinner";

const inputClass =
  "w-full rounded-lg border border-neutral-300 bg-white px-3 py-2 text-sm text-neutral-900 shadow-sm outline-none transition focus:border-brand-500 focus:ring-2 focus:ring-brand-500/30 dark:border-neutral-700 dark:bg-neutral-950 dark:text-neutral-100";
const labelClass =
  "mb-1 block text-xs font-medium text-neutral-600 dark:text-neutral-400";

function todayISO(): string {
  // Local (pt-BR) calendar date, not UTC — otherwise late-evening BR (UTC-3) rolls
  // to tomorrow and would accept a locally-future-dated trade.
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(
    d.getDate(),
  ).padStart(2, "0")}`;
}

/** Parse a possibly comma-decimal string to a number (`""` / invalid → NaN). */
function toNumber(raw: string): number {
  if (raw.trim() === "") return Number.NaN;
  return Number(raw.replace(",", "."));
}

interface ImportPageTradeFormProps {
  /** id of the shared `<datalist>` (held tickers) rendered by the page. */
  datalistId: string;
}

/**
 * "Adicionar operação" — create a manual trade. Ticker autocompletes from the
 * page's held-ticker `<datalist>` (free entry allowed), the total updates live,
 * and submit posts to `POST /api/trades` (invalidating positions / evolution /
 * trades / import-status).
 */
export function ImportPageTradeForm({ datalistId }: ImportPageTradeFormProps) {
  const addTrade = useAddTrade();
  const queryClient = useQueryClient();
  const { notify } = useToast();

  const [ticker, setTicker] = useState("");
  const [tradeDate, setTradeDate] = useState(todayISO);
  const [side, setSide] = useState<TradeSide>("buy");
  const [quantity, setQuantity] = useState("");
  const [price, setPrice] = useState("");
  const [institution, setInstitution] = useState("");
  const [note, setNote] = useState("");
  const [formError, setFormError] = useState<string | null>(null);

  const qtyNum = toNumber(quantity);
  const priceNum = toNumber(price);
  const total =
    qtyNum > 0 && priceNum > 0 ? qtyNum * priceNum : null;

  const errorMessage =
    formError ?? (addTrade.isError ? extractErrorMessage(addTrade.error) : null);

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    setFormError(null);

    const canonical = ticker.trim().toUpperCase();
    if (!canonical) {
      setFormError("Informe o código do ativo (ex.: PETR4).");
      return;
    }
    if (!tradeDate) {
      setFormError("Informe a data da operação.");
      return;
    }
    if (tradeDate > todayISO()) {
      setFormError("A data da operação não pode ser futura.");
      return;
    }
    if (!(qtyNum > 0)) {
      setFormError("A quantidade deve ser maior que zero.");
      return;
    }
    if (!(priceNum > 0)) {
      setFormError("O preço deve ser maior que zero.");
      return;
    }

    const payload: TradeInput = {
      trade_date: tradeDate,
      ticker: canonical,
      side,
      quantity: qtyNum,
      price: priceNum,
      ...(institution.trim() ? { institution: institution.trim() } : {}),
      ...(note.trim() ? { note: note.trim() } : {}),
    };

    addTrade.mutate(payload, {
      onSuccess: (trade) => {
        // The shared hook refreshes trades/positions/evolution; also refresh the
        // import status so the transactions row-count reflects the new manual row.
        void queryClient.invalidateQueries({ queryKey: queryKeys.importStatus });
        notify(
          `${trade.side === "sell" ? "Venda" : "Compra"} de ${trade.quantity} ${
            trade.ticker
          } registrada.`,
          "success",
        );
        setQuantity("");
        setPrice("");
        setNote("");
      },
    });
  };

  return (
    <Card title="Adicionar operação">
      <form onSubmit={handleSubmit} className="space-y-4" noValidate>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {/* Ticker */}
          <div className="sm:col-span-1">
            <label htmlFor="trade-ticker" className={labelClass}>
              Ativo
            </label>
            <input
              id="trade-ticker"
              list={datalistId}
              value={ticker}
              onChange={(e) => setTicker(e.target.value.toUpperCase())}
              placeholder="PETR4"
              autoComplete="off"
              className={clsx(inputClass, "font-mono uppercase")}
            />
          </div>

          {/* Date */}
          <div>
            <label htmlFor="trade-date" className={labelClass}>
              Data
            </label>
            <input
              id="trade-date"
              type="date"
              value={tradeDate}
              max={todayISO()}
              onChange={(e) => setTradeDate(e.target.value)}
              className={inputClass}
            />
          </div>

          {/* Side */}
          <div>
            <span className={labelClass}>Tipo</span>
            <div
              role="group"
              aria-label="Tipo de operação"
              className="grid grid-cols-2 gap-2"
            >
              <SideButton
                active={side === "buy"}
                side="buy"
                onClick={() => setSide("buy")}
              />
              <SideButton
                active={side === "sell"}
                side="sell"
                onClick={() => setSide("sell")}
              />
            </div>
          </div>

          {/* Quantity */}
          <div>
            <label htmlFor="trade-qty" className={labelClass}>
              Quantidade
            </label>
            <input
              id="trade-qty"
              type="text"
              inputMode="decimal"
              autoComplete="off"
              value={quantity}
              onChange={(e) => setQuantity(e.target.value)}
              placeholder="100"
              className={clsx(inputClass, "tabular-nums")}
            />
          </div>

          {/* Price */}
          <div>
            <label htmlFor="trade-price" className={labelClass}>
              Preço unitário
            </label>
            <input
              id="trade-price"
              type="text"
              inputMode="decimal"
              autoComplete="off"
              value={price}
              onChange={(e) => setPrice(e.target.value)}
              placeholder="28,50"
              className={clsx(inputClass, "tabular-nums")}
            />
          </div>

          {/* Institution */}
          <div>
            <label htmlFor="trade-institution" className={labelClass}>
              Instituição <span className="text-neutral-400">(opcional)</span>
            </label>
            <input
              id="trade-institution"
              value={institution}
              onChange={(e) => setInstitution(e.target.value)}
              placeholder="Corretora"
              className={inputClass}
            />
          </div>

          {/* Note */}
          <div className="sm:col-span-2">
            <label htmlFor="trade-note" className={labelClass}>
              Observação <span className="text-neutral-400">(opcional)</span>
            </label>
            <input
              id="trade-note"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="ex.: backfill de operação antiga"
              className={inputClass}
            />
          </div>
        </div>

        {/* Live total + submit */}
        <div className="flex flex-wrap items-end justify-between gap-4 border-t border-neutral-200 pt-4 dark:border-neutral-800">
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
              Total da operação
            </p>
            <p
              className={clsx(
                "mt-0.5 text-2xl font-semibold tabular-nums",
                total != null
                  ? "text-neutral-900 dark:text-neutral-50"
                  : "text-neutral-400 dark:text-neutral-600",
              )}
            >
              {total != null ? formatBRL(total) : "—"}
            </p>
          </div>
          <button
            type="submit"
            disabled={addTrade.isPending}
            className="inline-flex items-center gap-2 rounded-lg bg-brand-600 px-5 py-2.5 text-sm font-medium text-white shadow-sm transition-colors hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {addTrade.isPending ? (
              <LoadingSpinner className="h-4 w-4 border-white" />
            ) : (
              <span aria-hidden>＋</span>
            )}
            Registrar operação
          </button>
        </div>

        {errorMessage && (
          <p
            role="alert"
            className="rounded-lg border border-rose-300 bg-rose-50 px-3 py-2 text-sm text-rose-700 dark:border-rose-800 dark:bg-rose-950/50 dark:text-rose-300"
          >
            {errorMessage}
          </p>
        )}
      </form>
    </Card>
  );
}

function SideButton({
  active,
  side,
  onClick,
}: {
  active: boolean;
  side: TradeSide;
  onClick: () => void;
}) {
  const isBuy = side === "buy";
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={clsx(
        "flex items-center justify-center gap-1 rounded-lg border px-3 py-2 text-sm font-medium transition-colors",
        active && isBuy &&
          "border-emerald-500 bg-emerald-50 text-emerald-700 dark:border-emerald-500 dark:bg-emerald-950/60 dark:text-emerald-300",
        active && !isBuy &&
          "border-rose-500 bg-rose-50 text-rose-700 dark:border-rose-500 dark:bg-rose-950/60 dark:text-rose-300",
        !active &&
          "border-neutral-300 text-neutral-500 hover:bg-neutral-50 dark:border-neutral-700 dark:text-neutral-400 dark:hover:bg-neutral-800",
      )}
    >
      <span aria-hidden>{isBuy ? "↑" : "↓"}</span>
      {isBuy ? "Compra" : "Venda"}
    </button>
  );
}
