import { loadAdminNamespaces } from "@shared/lib";

// Словари операционных экранов: файлы locales/<lng>/admin/ops.json и соседние. В админке их грузит
// оболочка по маршруту раздела (pages/AdminPage/AdminApp.tsx); галерея разработчика и
// тесты грузят весь набор раздела этой функцией. runnerSsh в админке подключает само окно
// установки по SSH при открытии (ui/SshInstallDialog.tsx).
export const ensureAdminOpsLocales = (): Promise<void> =>
  loadAdminNamespaces([
    "ops",
    "runners",
    "runnerInstall",
    "runnerSsh",
    "runnerIsolation",
    "quotas",
    "services",
    "storage",
    "data",
  ]);
