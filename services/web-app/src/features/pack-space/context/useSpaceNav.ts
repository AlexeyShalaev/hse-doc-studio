import { useMemo } from "react";
import { buildSpaceUrl, isMove, type SpaceNavPatch } from "./nav";
import { useSpace } from "./SpaceContext";

export type SpaceNav = {
  /** Адрес после `patch`: для `<Link to>`. */
  href: (patch?: SpaceNavPatch) => string;
  /**
   * Перейти. Смена вкладки или версии идёт в историю, правка состояния внутри вкладки заменяет
   * запись; `push` переопределяет.
   */
  go: (patch: SpaceNavPatch, options?: { push?: boolean }) => void;
};

/** Единственный способ менять адрес из срезов (pack-studio-ux.md, 8.4). */
export const useSpaceNav = (): SpaceNav => {
  const { workspace, versionRef, tab, location } = useSpace();
  return useMemo(() => {
    const here = {
      workspaceId: workspace.id,
      ref: versionRef,
      tab,
      search: location.search,
    };
    return {
      href: (patch) => buildSpaceUrl(here, patch),
      go: (patch, options) => {
        location.navigate(buildSpaceUrl(here, patch), {
          replace: !(options?.push ?? isMove(here, patch)),
        });
      },
    };
  }, [workspace.id, versionRef, tab, location]);
};
