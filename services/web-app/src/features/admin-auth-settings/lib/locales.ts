import { loadAdminNamespaces } from "@shared/lib";

// Словари настроек входа: файлы locales/<lng>/admin/settings.json. В админке их грузит
// оболочка по маршруту раздела (pages/AdminPage/AdminApp.tsx); галерея разработчика и
// тесты грузят весь набор раздела этой функцией.
export const ensureAdminSettingsLocales = (): Promise<void> =>
  loadAdminNamespaces(["settings"]);
