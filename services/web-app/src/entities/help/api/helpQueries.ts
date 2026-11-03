import { useQuery } from "@tanstack/react-query";
import type { Lang } from "@shared/api";
import { helpApi, type HelpArticle, type HelpMap } from "./helpApi";

export const helpKeys = {
  all: ["help"] as const,
  map: (lang: Lang) => [...helpKeys.all, "map", lang] as const,
  article: (lang: Lang, key: string) =>
    [...helpKeys.all, "article", lang, key] as const,
};

// Справка меняется вместе с версией Студии, а не от действий человека: час свежести ничего не стоит,
// а повторы на отсутствующем файле никому не помогут (экран без статьи — нормальное состояние).
const STALE_TIME_MS = 60 * 60 * 1000;

export const useHelpMap = (lang: Lang, enabled = true) =>
  useQuery<HelpMap>({
    queryKey: helpKeys.map(lang),
    queryFn: ({ signal }) => helpApi.getMap(lang, signal),
    staleTime: STALE_TIME_MS,
    retry: false,
    enabled,
  });

export const useHelpArticle = (
  lang: Lang,
  key: string | undefined,
  enabled: boolean,
) =>
  useQuery<HelpArticle>({
    queryKey: helpKeys.article(lang, key ?? ""),
    queryFn: ({ signal }) => helpApi.getArticle(lang, key ?? "", signal),
    enabled: enabled && Boolean(key),
    staleTime: STALE_TIME_MS,
    retry: false,
  });
