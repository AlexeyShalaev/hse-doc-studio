import { isGitDetectedBy, type GitProviderInfo } from "@entities/git-sync";
import { isGitProvider, type GitHostSettings } from "../api/gitRemoteSchemas";
import { detectProvider, type ProviderDetection } from "./providerCatalog";

// Какой это сервер, с учётом того, что человек уже говорил про этот хост. Порядок
// тот же, что у сервера: выбор человека, имя хоста, ответ API, иначе other.
// Выбор живёт в настройках хоста (GET /git/hosts/settings), поэтому до ответа
// сервера остаётся определение по имени хоста: ни одно из них не требует сети.

export const hostKey = (host: string, port: number | null): string =>
  port === null ? host.toLowerCase() : `${host.toLowerCase()}:${String(port)}`;

/** Настройки хоста: сначала с тем же портом, затем без порта. */
export const findHostSettings = (
  list: readonly GitHostSettings[] | undefined,
  host: string | null,
  port: number | null,
): GitHostSettings | null => {
  if (!list || !host) return null;
  const name = host.toLowerCase();
  const sameHost = list.filter((item) => item.host.toLowerCase() === name);
  return (
    sameHost.find((item) => (item.port ?? null) === port) ??
    sameHost.find((item) => item.port === null || item.port === undefined) ??
    null
  );
};

const fromInfo = (
  info: GitProviderInfo | null | undefined,
): ProviderDetection | null => {
  if (!info || !isGitProvider(info.id) || !isGitDetectedBy(info.detected_by)) {
    return null;
  }
  return {
    id: info.id,
    detected_by: info.detected_by,
    version: info.version ?? null,
  };
};

/**
 * Провайдер хоста для показа. `known` это то, что сервер сказал о нём недавно
 * (ответ проверки адреса); выбор человека сильнее любого определения.
 */
export const providerOfHost = (
  host: string | null,
  port: number | null,
  settings: readonly GitHostSettings[] | undefined,
  known?: GitProviderInfo | null,
): ProviderDetection => {
  const saved = findHostSettings(settings, host, port);
  const override = saved?.provider_override;
  if (saved && override && isGitProvider(override)) {
    const info = fromInfo(saved.provider_info);
    return {
      id: override,
      detected_by: "override",
      version: info?.id === override ? info.version : null,
    };
  }
  const fresh = fromInfo(known);
  if (fresh && fresh.detected_by !== "unknown") return fresh;
  const stored = saved ? fromInfo(saved.provider_info) : null;
  if (stored && stored.detected_by !== "unknown") return stored;
  const local = detectProvider(host);
  // Версию сервера знает только он сам: берём её, если провайдер тот же.
  const version = [fresh, stored].find(
    (item) => item?.id === local.id && item.version,
  )?.version;
  return { ...local, version: version ?? null };
};
