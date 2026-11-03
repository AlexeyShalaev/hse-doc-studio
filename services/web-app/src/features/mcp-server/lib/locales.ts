import { loadAdminNamespaces } from "@shared/lib";

// Словарь страницы админки: locales/<lng>/admin/mcp.json. Тексты панели общие
// с настройками локальной Студии и лежат в основном словаре mcp.json.
export const ensureAdminMcpLocales = (): Promise<void> =>
  loadAdminNamespaces(["mcp"]);
