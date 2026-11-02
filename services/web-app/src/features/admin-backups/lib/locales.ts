import { loadAdminNamespaces } from "@shared/lib";

// Словари бэкапов: файлы locales/<lng>/admin/backups.json. В админке их грузит
// оболочка по маршруту раздела (pages/AdminPage/AdminApp.tsx); галерея разработчика и
// тесты грузят весь набор раздела этой функцией.
export const ensureAdminBackupsLocales = (): Promise<void> =>
  loadAdminNamespaces(["backups"]);
