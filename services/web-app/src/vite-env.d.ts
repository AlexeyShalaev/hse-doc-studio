/// <reference types="vite/client" />

// Версия из package.json, подставляется vite.config.ts через define.
declare const __APP_VERSION__: string;

// Включает демо синхронизации по git: ответы по git, профилю и доступам отдаёт
// память вкладки, остальное идёт настоящему бэкенду. Запуск: VITE_GIT_DEMO=1 pnpm dev.
// Слияние с интерфейсом из vite/client возможно только через interface.
// eslint-disable-next-line @typescript-eslint/consistent-type-definitions
interface ImportMetaEnv {
  readonly VITE_GIT_DEMO?: string;
  // Демо серверного режима: вход и сессия на данных вкладки. VITE_SERVER_DEMO=1 pnpm dev.
  readonly VITE_SERVER_DEMO?: string;
}
