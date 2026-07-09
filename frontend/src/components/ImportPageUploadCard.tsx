import { useRef, useState } from "react";
import clsx from "clsx";

import { extractErrorMessage } from "../api/client";
import { useImportFile } from "../api/hooks";
import type { ImportKind, TableStatus } from "../api/types";
import { formatDate } from "../lib/format";
import { useToast } from "../lib/toast";
import { Card } from "./Card";
import { LoadingSpinner } from "./LoadingSpinner";

interface ImportPageUploadCardProps {
  kind: ImportKind;
  /** Human title, e.g. "Resumo de Negociação". */
  title: string;
  /** Source sheet name inside the B3 workbook. */
  sheet: string;
  /** One-line explanation of what the file feeds. */
  description: string;
  /** Current row-count / last-imported status for this table. */
  status?: TableStatus;
  /** True while the import-status query is still loading. */
  statusLoading?: boolean;
}

/**
 * A single B3 export uploader. Owns its own file selection + `useImportFile`
 * mutation so each of the three cards has independent pending / error state.
 */
export function ImportPageUploadCard({
  kind,
  title,
  sheet,
  description,
  status,
  statusLoading,
}: ImportPageUploadCardProps) {
  const importFile = useImportFile();
  const { notify } = useToast();
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);

  const rows = status?.rows ?? 0;
  const lastImportedAt = status?.last_imported_at ?? null;
  const loaded = rows > 0;

  const handleSubmit = () => {
    if (!file) return;
    importFile.mutate(
      { kind, file },
      {
        onSuccess: (summary) => {
          notify(
            `${title}: ${summary.rows_imported} linha(s) importada(s).`,
            "success",
          );
          setFile(null);
          if (inputRef.current) inputRef.current.value = "";
        },
      },
    );
  };

  return (
    <Card
      title={title}
      action={
        <span
          className={clsx(
            "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium",
            loaded
              ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300"
              : "bg-neutral-100 text-neutral-500 dark:bg-neutral-800 dark:text-neutral-400",
          )}
        >
          {loaded ? "Carregado" : "Vazio"}
        </span>
      }
    >
      <div className="flex h-full flex-col gap-3">
        <p className="text-sm text-neutral-600 dark:text-neutral-300">
          {description}
        </p>
        <p className="text-xs text-neutral-400 dark:text-neutral-500">
          Aba <code className="font-mono">{sheet}</code> · arquivo{" "}
          <code className="font-mono">.xlsx</code>
        </p>

        <label
          className={clsx(
            "flex cursor-pointer items-center gap-2 rounded-lg border border-dashed px-3 py-2 text-sm transition-colors",
            "border-neutral-300 text-neutral-600 hover:border-brand-500 hover:text-brand-600",
            "dark:border-neutral-700 dark:text-neutral-300 dark:hover:border-brand-400 dark:hover:text-brand-300",
          )}
        >
          <input
            ref={inputRef}
            type="file"
            accept=".xlsx"
            className="sr-only"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
          <span aria-hidden>📎</span>
          <span className="truncate">
            {file ? file.name : "Escolher arquivo…"}
          </span>
        </label>

        {importFile.isError && (
          <p className="text-xs text-rose-600 dark:text-rose-400">
            {extractErrorMessage(importFile.error)}
          </p>
        )}

        <div className="mt-auto flex items-center justify-between gap-3 pt-1">
          <p className="min-w-0 text-xs text-neutral-500 dark:text-neutral-400">
            {statusLoading ? (
              "Carregando status…"
            ) : loaded ? (
              <>
                <span className="font-medium tabular-nums text-neutral-700 dark:text-neutral-200">
                  {rows.toLocaleString("pt-BR")}
                </span>{" "}
                linha(s)
                {lastImportedAt && (
                  <> · atualizado em {formatDate(lastImportedAt)}</>
                )}
              </>
            ) : (
              "Nenhum arquivo importado."
            )}
          </p>
          <button
            type="button"
            onClick={handleSubmit}
            disabled={!file || importFile.isPending}
            className="inline-flex shrink-0 items-center gap-2 rounded-lg bg-brand-600 px-3 py-2 text-sm font-medium text-white shadow-sm transition-colors hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {importFile.isPending ? (
              <LoadingSpinner className="h-4 w-4 border-white" />
            ) : (
              <span aria-hidden>⬆</span>
            )}
            {loaded ? "Reimportar" : "Importar"}
          </button>
        </div>
      </div>
    </Card>
  );
}
