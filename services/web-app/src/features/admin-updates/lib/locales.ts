import { loadAdminNamespaces } from "@shared/lib";

// Словари обновлений: файлы locales/<lng>/admin/updates.json. В админке их грузит
// оболочка по маршруту раздела (pages/AdminPage/AdminApp.tsx); галерея разработчика и
// тесты грузят весь набор раздела этой функцией.
export const ensureAdminUpdatesLocales = (): Promise<void> =>
  loadAdminNamespaces(["updates"]);
