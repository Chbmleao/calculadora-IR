import type { ReactNode } from "react";

interface PageHeaderProps {
  title: string;
  description?: ReactNode;
  /** Optional right-aligned actions. */
  actions?: ReactNode;
}

/** Consistent per-page title block. */
export function PageHeader({ title, description, actions }: PageHeaderProps) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div>
        <h1 className="text-xl font-semibold text-neutral-900 dark:text-neutral-50">
          {title}
        </h1>
        {description != null && (
          <p className="mt-0.5 text-sm text-neutral-500 dark:text-neutral-400">
            {description}
          </p>
        )}
      </div>
      {actions}
    </div>
  );
}
