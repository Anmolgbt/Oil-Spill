/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Backend origin. Optional — oiltrace.ts falls back to http://localhost:8000. */
  readonly VITE_API_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
