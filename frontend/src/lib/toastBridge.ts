/**
 * Decouples non-React modules (the React Query cache handlers in
 * {@link file://./queryClient.ts}) from the React toast UI. The
 * {@link file://./toast.tsx | ToastProvider} registers a notifier on mount;
 * callers emit through {@link emitToast} without importing React context.
 */
export type ToastVariant = "error" | "success" | "info";

type Notifier = (message: string, variant?: ToastVariant) => void;

let notifier: Notifier | null = null;

/** Registered by ToastProvider. Pass `null` to unregister on unmount. */
export function setToastNotifier(next: Notifier | null): void {
  notifier = next;
}

/** Emit a toast if a provider is mounted; a no-op otherwise. */
export function emitToast(message: string, variant: ToastVariant = "info"): void {
  notifier?.(message, variant);
}
