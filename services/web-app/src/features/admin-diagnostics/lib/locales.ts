import { loadAdminNamespaces } from "@shared/lib";

// Словари самодиагностики: файлы locales/<lng>/admin/diagnostics.json. В админке их грузит
// оболочка по маршруту раздела (pages/AdminPage/AdminApp.tsx); галерея разработчика и
// тесты грузят весь набор раздела этой функцией.
export const ensureAdminDiagnosticsLocales = (): Promise<void> =>
  loadAdminNamespaces(["diagnostics"]);
