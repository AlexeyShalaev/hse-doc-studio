import type { GitProvider } from "@entities/git-remote";
import { parseRemoteUrl, type ParsedRemoteUrl } from "./parseRemoteUrl";

// Условный адрес репозитория на сервере: у доступа есть только хост, а ссылкам на
// страницы сервера нужен разобранный адрес. Подставляем owner/repo и провайдера,
// которого человек выбрал (или определили по хосту).
export const urlForHost = (
  host: string,
  provider: GitProvider,
  port: number | null = null,
): ParsedRemoteUrl => {
  const authority = port ? `${host}:${String(port)}` : host;
  const parsed = parseRemoteUrl(`https://${authority}/owner/repo`);
  const base: ParsedRemoteUrl = parsed.ok
    ? parsed.url
    : {
        display_url: `https://${authority}`,
        kind: "https",
        host,
        port,
        user: null,
        provider,
        owner: null,
        repo: null,
        path: "",
        token_stripped: false,
      };
  return { ...base, provider };
};

const HOST_ONLY = /^[a-z0-9]([a-z0-9.-]*[a-z0-9])?(:\d{1,5})?$/i;

/**
 * Сервер для нового токена по тому, что ввёл человек: имя сервера
 * (github.com, gitlab.hse.ru:8443) или адрес репозитория целиком. Для адреса
 * репозитория остаются владелец и имя (ссылка на токен подставит владельца);
 * для имени сервера их нет. null: разобрать нельзя.
 */
export const targetOfAddress = (input: string): ParsedRemoteUrl | null => {
  const value = input.trim().replace(/\/+$/, "");
  if (value === "") return null;
  if (HOST_ONLY.test(value)) {
    const parsed = parseRemoteUrl(`https://${value}/owner/repo`);
    return parsed.ok
      ? {
          ...parsed.url,
          display_url: `https://${value}`,
          owner: null,
          repo: null,
          path: "",
        }
      : null;
  }
  const parsed = parseRemoteUrl(value, { allow_http: true });
  return parsed.ok && parsed.url.kind !== "file" && parsed.url.host
    ? parsed.url
    : null;
};
