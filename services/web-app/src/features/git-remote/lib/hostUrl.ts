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
