import { apiClient } from "./client";
import { isDemoTransport } from "./demo";

/**
 * Начало серверного сценария, который идёт переходом браузера (вход через провайдера, привязка).
 * Возвращает адрес перехода. Демо-мир перейти не может, поэтому там сценарий проходит запросом,
 * а адрес приходит в ответе.
 */
export const startRedirectFlow = async (
  path: string,
  options: { silentError: true },
): Promise<{ redirect_url: string }> => {
  if (isDemoTransport(apiClient)) {
    const res = await apiClient.get<{ redirect_url: string }>(path, options);
    return { redirect_url: res.data.redirect_url };
  }
  const base = apiClient.defaults.baseURL ?? "/api/v1";
  return {
    redirect_url: `${base}${path}?next=${encodeURIComponent(window.location.pathname)}`,
  };
};
