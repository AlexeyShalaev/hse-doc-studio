import { loadAdminNamespaces } from "@shared/lib";

// Словари журнала писем: admin/mail.json и подписи видов писем из admin/settings.json
// (`mailPreview.names.*`, их не копируем: тест настроек следит, что у каждого вида есть подпись).
// В админке их грузит оболочка по маршруту /admin/mail; галерея и тесты зовут эту функцию.
export const ensureAdminMailLocales = (): Promise<void> =>
  loadAdminNamespaces(["mail", "settings"]);
