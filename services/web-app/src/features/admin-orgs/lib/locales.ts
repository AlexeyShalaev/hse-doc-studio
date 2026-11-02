import { loadAdminNamespaces } from "@shared/lib";

// Словари организаций: файлы locales/<lng>/admin/orgs.json. В админке их грузит
// оболочка по маршруту раздела (pages/AdminPage/AdminApp.tsx); галерея разработчика и
// тесты грузят весь набор раздела этой функцией.
export const ensureAdminOrgsLocales = (): Promise<void> =>
  loadAdminNamespaces(["orgs"]);
