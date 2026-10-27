import { useMemo } from "react";
import {
  providerOfHost,
  useHostSettings,
  useUpdateHostSettings,
  type GitProvider,
  type ProviderDetection,
} from "@entities/git-remote";
import type { GitProviderInfo } from "@entities/git-sync";
import type { ParsedRemoteUrl } from "../lib/parseRemoteUrl";
import { useInstancePathStore } from "./useInstancePathStore";

// Порт сайта: у ssh он относится к ssh, а не к сайту, поэтому настройки хоста
// от него не зависят.
const sitePort = (url: ParsedRemoteUrl | null): number | null =>
  url && (url.kind === "https" || url.kind === "http") ? url.port : null;

// Что за сервер у этого адреса: выбор человека, имя хоста, ответ API. Возвращает
// и адрес с уже подставленным провайдером, чтобы подсказки и ссылки ниже
// работали с тем, что решено, а не с тем, что угадал разбор адреса.
export const useHostProvider = (
  url: ParsedRemoteUrl | null,
  known?: GitProviderInfo | null,
) => {
  const host = url && url.kind !== "file" ? url.host : null;
  const port = sitePort(url);
  const settings = useHostSettings(host !== null);
  const update = useUpdateHostSettings();
  const subpath = useInstancePathStore((state) =>
    host ? (state.paths[host.toLowerCase()] ?? "") : "",
  );
  const setPath = useInstancePathStore((state) => state.setPath);

  const detection: ProviderDetection = useMemo(
    () => providerOfHost(host, port, settings.data, known),
    [host, port, settings.data, known],
  );
  const effectiveUrl = useMemo(
    () =>
      url && url.provider !== detection.id
        ? { ...url, provider: detection.id }
        : url,
    [url, detection.id],
  );

  return {
    detection,
    url: effectiveUrl,
    host,
    port,
    subpath,
    setSubpath: (path: string): void => {
      if (host) setPath(host, path);
    },
    /** null возвращает определение по умолчанию. */
    setOverride: (provider: GitProvider | null) => {
      if (!host) return Promise.resolve(null);
      return update.mutateAsync({
        host,
        port,
        provider_override: provider,
      });
    },
    isSaving: update.isPending,
    error: update.error,
    resetError: update.reset,
  };
};

export type HostProvider = ReturnType<typeof useHostProvider>;
