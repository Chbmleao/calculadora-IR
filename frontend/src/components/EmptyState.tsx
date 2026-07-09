import type { ReactNode } from "react";

interface EmptyStateProps {
  title: string;
  description?: ReactNode;
  /** Decorative icon (e.g. an emoji). */
  icon?: ReactNode;
  /** Optional call-to-action. */
  action?: ReactNode;
}

/** Neutral placeholder shown when a screen has no data yet. */
export function EmptyState({ title, description, icon, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-neutral-300 bg-neutral-50 px-6 py-16 text-center dark:border-neutral-700 dark:bg-neutral-900/50">
      {icon != null && <div className="text-3xl">{icon}</div>}
      <h3 className="text-base font-semibold text-neutral-700 dark:text-neutral-200">
        {title}
      </h3>
      {description != null && (
        <p className="max-w-md text-sm text-neutral-500 dark:text-neutral-400">
          {description}
        </p>
      )}
      {action}
    </div>
  );
}
