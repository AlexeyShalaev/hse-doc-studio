import { useMemo } from "react";
import { useLocation } from "react-router";
import { rankHelpKeys, useHelpMap } from "@entities/help";
import { useThemeStore } from "@shared/lib";

/** Статьи текущего экрана по карте справки, самая подходящая первой. Карта грузится по `enabled`. */
export const useCurrentHelpKeys = (enabled: boolean): string[] => {
  const { pathname, search } = useLocation();
  const lang = useThemeStore((s) => s.lang);
  const { data: map } = useHelpMap(lang, enabled);
  return useMemo(
    () => (map ? rankHelpKeys(map, pathname, search) : []),
    [map, pathname, search],
  );
};
