import { loadAdminNamespaces } from "@shared/lib";

// Словарь страницы: locales/<lng>/admin/modelServers.json (в админке его грузит оболочка по маршруту).
export const ensureAdminModelServersLocales = (): Promise<void> =>
  loadAdminNamespaces(["modelServers"]);
