import type { ReactNode } from "react";
import clsx from "clsx";

interface CardProps {
  children: ReactNode;
  className?: string;
  /** Optional header title. */
  title?: ReactNode;
  /** Optional header action (right-aligned), e.g. a button or badge. */
  action?: ReactNode;
  /** Remove the default body padding (e.g. for edge-to-edge tables). */
  flush?: boolean;
}

/** Rounded, bordered surface used to group content. Legible in light and dark. */
export function Card({ children, className, title, action, flush }: CardProps) {
  return (
    <section
      className={clsx(
        "rounded-xl border border-neutral-200 bg-white shadow-sm",
        "dark:border-neutral-800 dark:bg-neutral-900",
        className,
      )}
    >
      {(title != null || action != null) && (
        <header className="flex items-center justify-between gap-3 border-b border-neutral-200 px-4 py-3 dark:border-neutral-800">
          {title != null ? (
            <h2 className="text-sm font-semibold text-neutral-700 dark:text-neutral-200">
              {title}
            </h2>
          ) : (
            <span />
          )}
          {action}
        </header>
      )}
      <div className={clsx(!flush && "p-4")}>{children}</div>
    </section>
  );
}
