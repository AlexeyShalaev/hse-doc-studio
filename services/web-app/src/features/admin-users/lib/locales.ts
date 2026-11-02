import { loadAdminNamespaces } from "@shared/lib";

// Словари людей и аудита: файлы locales/<lng>/admin/users.json и соседние. В админке их грузит
// оболочка по маршруту раздела (pages/AdminPage/AdminApp.tsx); галерея разработчика и
// тесты грузят весь набор раздела этой функцией.
export const ensureAdminUsersLocales = (): Promise<void> =>
  loadAdminNamespaces(["users", "audit"]);
