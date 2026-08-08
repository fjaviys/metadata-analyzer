/// <reference path="../.astro/types.d.ts" />
/// <reference types="astro/client" />

interface ImportMetaEnv {
  readonly PUBLIC_API_BASE_URL?: string;
  readonly PUBLIC_WS_BASE_URL?: string;
}
interface ImportMeta {
  readonly env: ImportMetaEnv;
}
