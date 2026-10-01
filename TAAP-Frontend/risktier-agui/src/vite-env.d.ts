/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Base URL of the FastAPI backend (app/api/api.py). Defaults to http://127.0.0.1:4000. */
  readonly VITE_API_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
