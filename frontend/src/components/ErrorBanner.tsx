import type { ReactNode } from "react";

interface ErrorBannerProps {
  title?: string;
  message: ReactNode;
  /** Optional retry handler (renders a Retry button). */
  onRetry?: () => void;
}

/** Inline error surface for failed data loads. */
export function ErrorBanner({
  title = "Something went wrong",
  message,
  onRetry,
}: ErrorBannerProps) {
  return (
    <div
      role="alert"
      className="flex items-start justify-between gap-3 rounded-lg border border-rose-300 bg-rose-50 px-4 py-3 text-rose-800 dark:border-rose-800 dark:bg-rose-950/50 dark:text-rose-200"
    >
      <div className="min-w-0">
        <p className="text-sm font-semibold">{title}</p>
        <p className="mt-0.5 break-words text-sm">{message}</p>
      </div>
      {onRetry != null && (
        <button
          type="button"
          onClick={onRetry}
          className="shrink-0 rounded-md border border-rose-300 px-2 py-1 text-xs font-medium transition-colors hover:bg-rose-100 dark:border-rose-700 dark:hover:bg-rose-900"
        >
          Retry
        </button>
      )}
    </div>
  );
}
