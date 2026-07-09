/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Base URL of the FastAPI backend (see src/api/client.ts). */
  readonly VITE_API_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
