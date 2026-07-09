import clsx from "clsx";

interface LoadingSpinnerProps {
  /** Extra classes for the spinner element (e.g. size or border color). */
  className?: string;
  /** Optional label rendered next to the spinner. */
  label?: string;
}

/** Inline, accessible loading indicator. */
export function LoadingSpinner({ className, label }: LoadingSpinnerProps) {
  return (
    <div
      role="status"
      className="flex items-center justify-center gap-2 text-neutral-500 dark:text-neutral-400"
    >
      <span
        className={clsx(
          "inline-block h-5 w-5 animate-spin rounded-full border-2 border-current border-t-transparent",
          className,
        )}
      />
      {label != null && <span className="text-sm">{label}</span>}
    </div>
  );
}
