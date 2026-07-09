import { useMemo, useState } from "react";
import type { FormEvent } from "react";
import { Link } from "react-router-dom";
import clsx from "clsx";

import { extractErrorMessage } from "../api/client";
import {
  downloadAccountingXlsx,
  useAccounting,
  useSaveCnpj,
} from "../api/hooks";
import type {
  AccountingAsset,
  CnpjOverrideIn,
  MissingCnpjItem,
} from "../api/types";
import { Card } from "../components/Card";
import { EmptyState } from "../components/EmptyState";
import { ErrorBanner } from "../components/ErrorBanner";
import { LoadingSpinner } from "../components/LoadingSpinner";
import { PageHeader } from "../components/PageHeader";
import { StatTile } from "../components/StatTile";
import { formatBRL } from "../lib/format";
import { useToast } from "../lib/toast";

/* ── Column config (Portuguese keys pass through from `core.py`) ──────────── */

type ColumnKind = "text" | "mono" | "cnpj" | "money";

interface Column {
  /** Exact dict key emitted by the backend / `core.get_assets_and_rights`. */
  key: string;
  label: string;
  kind: ColumnKind;
  /** Full-text tooltip when the header is abbreviated. */
  title?: string;
  /** Allow the cell to wrap (used for the long "Discriminação" text). */
  wrap?: boolean;
}

const COLUMNS: Column[] = [
  { key: "Produto", label: "Produto", kind: "mono" },
  { key: "Grupo", label: "Grupo", kind: "text" },
  { key: "Código", label: "Código", kind: "text" },
  { key: "CNPJ", label: "CNPJ", kind: "cnpj" },
  { key: "Discriminação", label: "Discriminação", kind: "text", wrap: true },
  { key: "Situação final", label: "Situação final", kind: "money" },
  {
    key: "Juros Sobre Capital Próprio",
    label: "JCP",
    kind: "money",
    title: "Juros Sobre Capital Próprio",
  },
  { key: "Dividendo", label: "Dividendo", kind: "money" },
  { key: "Rendimento", label: "Rendimento", kind: "money" },
];

const PROVENTO_KEYS = [
  "Juros Sobre Capital Próprio",
  "Dividendo",
  "Rendimento",
];

const CNPJ_MISSING_SENTINEL = "Não encontrado";

/* ── Safe accessors for the open string map ──────────────────────────────── */

function readString(asset: AccountingAsset, key: string): string {
  const value = asset[key];
  return value == null ? "" : String(value);
}

function readNumber(asset: AccountingAsset, key: string): number {
  const value = asset[key];
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) ? n : 0;
}

/* ── Page ────────────────────────────────────────────────────────────────── */

/**
 * Bens e Direitos (DIRPF helper). Previews the "Bens e Direitos" sheet built by
 * `core.py`, lets the user fill missing CNPJs (persisted to the catalog), and
 * downloads the `.xlsx` — mirroring the legacy Streamlit `app.py` flow.
 */
export function AccountingPage() {
  const accounting = useAccounting();
  const assets = accounting.data?.assets ?? [];
  const missing = accounting.data?.missing_cnpj ?? [];
  const hasAssets = assets.length > 0;

  const totals = useMemo(() => {
    let patrimonio = 0;
    let proventos = 0;
    for (const asset of assets) {
      patrimonio += readNumber(asset, "Situação final");
      for (const key of PROVENTO_KEYS) proventos += readNumber(asset, key);
    }
    return { patrimonio, proventos };
  }, [assets]);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Bens e Direitos"
        description="Auxiliar da ficha do IRPF a partir dos extratos da B3."
        actions={
          <DownloadXlsxButton disabled={!hasAssets || accounting.isLoading} />
        }
      />

      <GuidanceCard />

      {accounting.isLoading && (
        <Card>
          <LoadingSpinner label="Gerando a prévia de Bens e Direitos…" />
        </Card>
      )}

      {accounting.isError && (
        <ErrorBanner
          title="Não foi possível gerar a prévia"
          message={extractErrorMessage(accounting.error)}
          onRetry={() => void accounting.refetch()}
        />
      )}

      {accounting.isSuccess && !hasAssets && (
        <EmptyState
          icon="🧾"
          title="Nada para declarar ainda"
          description="Importe o Resumo de Negociação e o extrato de Proventos para gerar a ficha Bens e Direitos."
          action={
            <Link
              to="/import"
              className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-blue-500 dark:bg-blue-500 dark:hover:bg-blue-400"
            >
              Ir para Importar
            </Link>
          }
        />
      )}

      {accounting.isSuccess && hasAssets && (
        <>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatTile
              label="Ativos"
              value={assets.length.toLocaleString("pt-BR")}
              hint="Linhas na ficha"
            />
            <StatTile
              label="Situação final (total)"
              value={formatBRL(totals.patrimonio)}
              hint="Soma em 31/12"
            />
            <StatTile
              label="Proventos (total)"
              value={formatBRL(totals.proventos)}
              hint="JCP + Dividendos + Rendimentos"
            />
            <StatTile
              label="Sem CNPJ"
              value={missing.length.toLocaleString("pt-BR")}
              hint={
                missing.length > 0 ? "Requer preenchimento" : "Catálogo completo"
              }
              trend={missing.length > 0 ? "down" : "up"}
            />
          </div>

          {missing.length > 0 && (
            <MissingCnpjEditor
              key={missing.map((item) => item.Produto).join("|")}
              items={missing}
            />
          )}

          <Card
            flush
            title={`Prévia — Bens e Direitos (${assets.length} ${
              assets.length === 1 ? "ativo" : "ativos"
            })`}
            action={
              <span className="text-xs text-neutral-500 dark:text-neutral-400">
                Valores em R$ (pt-BR)
              </span>
            }
          >
            <PreviewTable assets={assets} />
          </Card>
        </>
      )}
    </div>
  );
}

/* ── Guidance ────────────────────────────────────────────────────────────── */

function GuidanceCard() {
  return (
    <Card title="Como funciona">
      <div className="space-y-3 text-sm text-neutral-600 dark:text-neutral-300">
        <p>
          Auxiliar para a ficha <strong>Bens e Direitos</strong> do IRPF a partir
          dos extratos da B3 (área do investidor → Extrato → Proventos /
          Negociação).
        </p>
        <ul className="list-disc space-y-1 pl-5">
          <li>
            Importe o <strong>extrato de Proventos</strong> e o{" "}
            <strong>Resumo de Negociação</strong>.
          </li>
          <li>
            Use o período desde a <strong>primeira compra</strong> até{" "}
            <strong>31/12 do ano-base</strong>.
          </li>
          <li>
            Preencha os CNPJs faltantes para reaproveitá-los nas próximas
            execuções.
          </li>
        </ul>
        <p>
          Faltando dados?{" "}
          <Link
            to="/import"
            className="font-medium text-blue-600 underline-offset-2 hover:underline dark:text-blue-400"
          >
            Importe seus extratos
          </Link>
          .
        </p>
      </div>
    </Card>
  );
}

/* ── Download button ─────────────────────────────────────────────────────── */

function DownloadXlsxButton({ disabled }: { disabled?: boolean }) {
  const { notify } = useToast();
  const [downloading, setDownloading] = useState(false);

  const handleDownload = async () => {
    setDownloading(true);
    try {
      await downloadAccountingXlsx();
      notify("Download de Bens e Direitos iniciado.", "success");
    } catch (error) {
      notify(extractErrorMessage(error), "error");
    } finally {
      setDownloading(false);
    }
  };

  return (
    <button
      type="button"
      onClick={() => void handleDownload()}
      disabled={disabled || downloading}
      className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-blue-500 disabled:cursor-not-allowed disabled:opacity-60 dark:bg-blue-500 dark:hover:bg-blue-400"
    >
      <svg
        aria-hidden="true"
        viewBox="0 0 24 24"
        className="h-4 w-4"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M12 3v12" />
        <path d="m7 10 5 5 5-5" />
        <path d="M5 21h14" />
      </svg>
      {downloading ? "Gerando…" : "Baixar .xlsx"}
    </button>
  );
}

/* ── Missing-CNPJ inline editor ──────────────────────────────────────────── */

function MissingCnpjEditor({ items }: { items: MissingCnpjItem[] }) {
  const { notify } = useToast();
  const saveCnpj = useSaveCnpj();
  const [drafts, setDrafts] = useState<Record<string, string>>({});

  const filledCount = items.filter(
    (item) => (drafts[item.Produto] ?? "").trim() !== "",
  ).length;

  const handleChange = (produto: string, value: string) => {
    setDrafts((current) => ({ ...current, [produto]: value }));
  };

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    const rows: CnpjOverrideIn[] = items
      .filter((item) => (drafts[item.Produto] ?? "").trim() !== "")
      .map((item) => ({
        Ticker: item.Produto,
        Tipo: item.Grupo,
        CNPJ: (drafts[item.Produto] ?? "").trim(),
      }));

    if (rows.length === 0) {
      notify("Nenhum CNPJ preenchido — nada para salvar.", "error");
      return;
    }

    saveCnpj.mutate(rows, {
      onSuccess: (result) => {
        const n = result.saved;
        notify(
          `${n} ${n === 1 ? "CNPJ salvo" : "CNPJs salvos"} no catálogo.`,
          "success",
        );
      },
      // Errors are surfaced globally by the queryClient MutationCache.
    });
  };

  return (
    <Card flush>
      <form onSubmit={handleSubmit}>
        {/* Warning: status color paired with icon + text (never color alone). */}
        <div className="flex items-start gap-3 rounded-t-xl border-b border-amber-300 bg-amber-50 px-4 py-3 text-amber-900 dark:border-amber-700/60 dark:bg-amber-950/40 dark:text-amber-100">
          <span aria-hidden="true" className="mt-0.5 text-lg leading-none">
            ⚠️
          </span>
          <div>
            <p className="text-sm font-semibold">
              {items.length}{" "}
              {items.length === 1
                ? "ativo sem CNPJ no catálogo"
                : "ativos sem CNPJ no catálogo"}
            </p>
            <p className="mt-0.5 text-sm">
              Preencha abaixo e salve para reaproveitar nas próximas execuções.
              Pode colar com pontuação ou só dígitos.
            </p>
          </div>
        </div>

        <div className="space-y-3 p-4">
          {/* Header row (hidden on mobile, where fields stack). */}
          <div className="hidden gap-3 px-1 text-xs font-medium uppercase tracking-wide text-neutral-500 sm:grid sm:grid-cols-[8rem_1fr_18rem] dark:text-neutral-400">
            <span>Produto</span>
            <span>Grupo</span>
            <span>CNPJ</span>
          </div>

          {items.map((item) => (
            <div
              key={item.Produto}
              className="grid grid-cols-1 gap-2 sm:grid-cols-[8rem_1fr_18rem] sm:items-center"
            >
              <div className="font-mono text-sm font-medium text-neutral-900 dark:text-neutral-100">
                <span className="text-xs text-neutral-500 sm:hidden dark:text-neutral-400">
                  Produto:{" "}
                </span>
                {item.Produto}
              </div>
              <div className="text-sm text-neutral-500 dark:text-neutral-400">
                <span className="text-xs sm:hidden">Grupo: </span>
                {item.Grupo}
              </div>
              <input
                type="text"
                value={drafts[item.Produto] ?? ""}
                onChange={(event) =>
                  handleChange(item.Produto, event.target.value)
                }
                placeholder="00.000.000/0001-00 ou só dígitos"
                aria-label={`CNPJ para ${item.Produto}`}
                className="w-full rounded-md border border-neutral-300 bg-white px-3 py-1.5 text-sm tabular-nums text-neutral-900 shadow-sm outline-none transition-colors focus:border-blue-500 focus:ring-2 focus:ring-blue-500/30 dark:border-neutral-700 dark:bg-neutral-950 dark:text-neutral-100"
              />
            </div>
          ))}

          <div className="flex flex-wrap items-center justify-between gap-3 pt-1">
            <p className="text-xs text-neutral-500 dark:text-neutral-400">
              {filledCount > 0
                ? `${filledCount} de ${items.length} preenchido(s)`
                : "Nenhum CNPJ preenchido ainda"}
            </p>
            <button
              type="submit"
              disabled={saveCnpj.isPending}
              className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-blue-500 disabled:cursor-not-allowed disabled:opacity-60 dark:bg-blue-500 dark:hover:bg-blue-400"
            >
              {saveCnpj.isPending ? "Salvando…" : "Salvar no catálogo"}
            </button>
          </div>
        </div>
      </form>
    </Card>
  );
}

/* ── Preview table ───────────────────────────────────────────────────────── */

function PreviewTable({ assets }: { assets: AccountingAsset[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[960px] border-collapse text-sm">
        <thead>
          <tr className="border-b border-neutral-200 text-left text-xs uppercase tracking-wide text-neutral-500 dark:border-neutral-800 dark:text-neutral-400">
            {COLUMNS.map((col) => (
              <th
                key={col.key}
                scope="col"
                title={col.title}
                className={clsx(
                  "whitespace-nowrap px-3 py-2 font-medium",
                  col.kind === "money" && "text-right",
                )}
              >
                {col.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {assets.map((asset, index) => (
            <tr
              key={`${readString(asset, "Produto")}-${index}`}
              className="border-b border-neutral-100 transition-colors last:border-0 hover:bg-neutral-50 dark:border-neutral-800/60 dark:hover:bg-neutral-800/40"
            >
              {COLUMNS.map((col) => (
                <PreviewCell key={col.key} asset={asset} col={col} />
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function PreviewCell({
  asset,
  col,
}: {
  asset: AccountingAsset;
  col: Column;
}) {
  if (col.kind === "money") {
    return (
      <td className="whitespace-nowrap px-3 py-2 text-right tabular-nums text-neutral-800 dark:text-neutral-200">
        {formatBRL(readNumber(asset, col.key))}
      </td>
    );
  }

  if (col.kind === "cnpj") {
    const value = readString(asset, col.key);
    const isMissing = value === "" || value === CNPJ_MISSING_SENTINEL;
    return (
      <td className="whitespace-nowrap px-3 py-2">
        {isMissing ? (
          <span className="inline-flex items-center gap-1 rounded-full border border-amber-300 bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-800 dark:border-amber-700/60 dark:bg-amber-950/40 dark:text-amber-200">
            <span aria-hidden="true">⚠️</span>
            Não encontrado
          </span>
        ) : (
          <span className="font-mono text-neutral-800 dark:text-neutral-200">
            {value}
          </span>
        )}
      </td>
    );
  }

  const value = readString(asset, col.key);
  return (
    <td
      className={clsx(
        "px-3 py-2 text-neutral-800 dark:text-neutral-200",
        col.wrap ? "min-w-[18rem]" : "whitespace-nowrap",
        col.kind === "mono" &&
          "font-mono font-medium text-neutral-900 dark:text-neutral-100",
      )}
    >
      {value || "—"}
    </td>
  );
}
