import axios from "axios";

import type { ErrorResponse } from "./types";

/**
 * Base URL of the FastAPI backend. Read from `VITE_API_BASE_URL`
 * (`frontend/.env`), defaulting to the local dev server.
 */
export const API_BASE_URL: string =
  import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

/** Shared axios instance. All requests hit the backend under `/api`. */
export const api = axios.create({
  baseURL: API_BASE_URL,
  headers: { Accept: "application/json" },
});

/**
 * Normalize any request failure into a single user-facing message. Prefers the
 * backend's `{ "error": ... }` envelope (README §7), falls back to FastAPI's
 * `detail`, then to a friendly network message.
 */
export function extractErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const data = error.response?.data as
      | (Partial<ErrorResponse> & { detail?: unknown })
      | undefined;
    if (data && typeof data === "object") {
      if (typeof data.error === "string") return data.error;
      if (typeof data.detail === "string") return data.detail;
    }
    if (error.code === "ERR_NETWORK") {
      return "Cannot reach the API — is the backend running?";
    }
    return error.message;
  }
  if (error instanceof Error) return error.message;
  return "Unexpected error";
}

// Central error handling: every rejected request is re-thrown as a plain Error
// carrying a clean, user-facing message. React Query's cache surfaces those as
// toasts (see src/lib/queryClient.ts); pages can also render them inline.
api.interceptors.response.use(
  (response) => response,
  (error: unknown) => Promise.reject(new Error(extractErrorMessage(error))),
);

/* ── Typed request helpers ───────────────────────────────────────────────── */

export async function apiGet<T>(
  url: string,
  params?: Record<string, unknown>,
): Promise<T> {
  const { data } = await api.get<T>(url, { params });
  return data;
}

export async function apiPost<T>(url: string, body?: unknown): Promise<T> {
  const { data } = await api.post<T>(url, body);
  return data;
}

export async function apiPut<T>(url: string, body?: unknown): Promise<T> {
  const { data } = await api.put<T>(url, body);
  return data;
}

export async function apiPatch<T>(url: string, body?: unknown): Promise<T> {
  const { data } = await api.patch<T>(url, body);
  return data;
}

export async function apiDelete<T = void>(url: string): Promise<T> {
  const { data } = await api.delete<T>(url);
  return data;
}

/**
 * Multipart upload helper for Excel imports. POSTs `file` under field name
 * `file` to `/api/import/{kind}`.
 */
export async function apiUpload<T>(
  url: string,
  file: File,
  fieldName = "file",
): Promise<T> {
  const form = new FormData();
  form.append(fieldName, file);
  const { data } = await api.post<T>(url, form);
  return data;
}

/**
 * Fetch a streamed file (e.g. the Bens e Direitos `.xlsx`) as a Blob and
 * trigger a browser download. Runs through the shared axios instance so the
 * base URL and error handling stay consistent.
 */
export async function apiDownload(url: string, filename: string): Promise<void> {
  const { data } = await api.get<Blob>(url, { responseType: "blob" });
  const href = URL.createObjectURL(data);
  const anchor = document.createElement("a");
  anchor.href = href;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(href);
}
