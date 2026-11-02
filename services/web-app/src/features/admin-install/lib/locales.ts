import { loadAdminNamespaces } from "@shared/lib";

// Словари установки: файлы locales/<lng>/admin/install.json. В админке их грузит
// оболочка по маршруту раздела (pages/AdminPage/AdminApp.tsx); галерея разработчика и
// тесты грузят весь набор раздела этой функцией.
export const ensureAdminInstallLocales = (): Promise<void> =>
  loadAdminNamespaces(["install"]);
