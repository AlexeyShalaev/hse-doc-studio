import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import type {
  PackTreePack,
  PackTreeTemplate,
  PackVersionRef,
} from "@entities/pack-studio";
import { pickLocalized } from "@shared/lib";
import { useSpace } from "../context/SpaceContext";
import { useSpaceNav } from "../context/useSpaceNav";
import { readLastVersion } from "./lastVisited";
import {
  changedFilesOf,
  countByVersion,
  myChanges,
  type MyChange,
} from "./pickDefaultVersion";
import { refForPack, refForTemplate } from "./targets";
import { useMyChangedPaths } from "../changes/useChangesStatus";
import { useChangedPaths } from "./useChangedPaths";

// «Где я» для полос пространства и шторки «Куда перейти»: названия, списки пака, шаблона и версии,
// мои изменения и переходы. Один источник для десктопных крошек и телефонной шторки.

export type PackRow = {
  id: string;
  name: string;
  current: boolean;
  /** Открыть нечего: в паке нет шаблонов или ни у одного шаблона нет версий. */
  empty: "templates" | "versions" | null;
};
export type TemplateRow = {
  id: string;
  name: string;
  current: boolean;
  /** У шаблона нет версий: открыть нечего. */
  empty: boolean;
};
export type VersionRow = {
  version: string;
  current: boolean;
  released: boolean;
  isDefault: boolean;
  /** Сколько моих изменённых файлов в версии. */
  files: number;
};
export type MineRow = MyChange & { templateName: string; current: boolean };

export type Where = {
  packName: string;
  templateName: string;
  packs: PackRow[];
  templates: TemplateRow[];
  /** Новые сверху. */
  versions: VersionRow[];
  mine: MineRow[];
  /** Версии с моими изменениями, кроме открытой: то, к чему можно вернуться. */
  mineElsewhere: MineRow[];
  /** Папка пака на диске: нужна окну «Новый шаблон». */
  packDir: string;
  goPack: (id: string) => void;
  goTemplate: (id: string) => void;
  goVersion: (version: string) => void;
  goMine: (ref: PackVersionRef) => void;
};

const nameOf = (item: PackTreePack | PackTreeTemplate, lang: string): string =>
  pickLocalized(item.name ?? undefined, lang, item.id);

const sameRef = (a: PackVersionRef, b: PackVersionRef): boolean =>
  a.pack === b.pack && a.template === b.template && a.version === b.version;

export const useWhere = (): Where => {
  const { i18n } = useTranslation();
  const { workspace, tree, versionRef, pack, template } = useSpace();
  const nav = useSpaceNav();
  // Куда вести (версия с моей работой, в том числе свежая копия) решают файлы git как есть, а
  // числа «N файлов изменено» берутся из того же источника, что у панели «Изменения».
  const changed = useChangedPaths();
  const mineChanged = useMyChangedPaths();
  const lang = i18n.language;
  const wsId = workspace.id;

  return useMemo<Where>(() => {
    const counts = countByVersion(mineChanged);
    const lastOf = (p: string, t: string) => readLastVersion(wsId, p, t);
    const go = (ref: PackVersionRef | null) => {
      if (ref) nav.go({ ref });
    };
    const templateOf = (ref: PackVersionRef): PackTreeTemplate | undefined =>
      tree.packs
        .find((p) => p.id === ref.pack)
        ?.templates.find((t) => t.id === ref.template);
    const mine = myChanges(tree, mineChanged).map<MineRow>((item) => {
      const found = templateOf(item.ref);
      return {
        ...item,
        templateName: found ? nameOf(found, lang) : item.ref.template,
        current: sameRef(item.ref, versionRef),
      };
    });
    return {
      packName: pack ? nameOf(pack, lang) : versionRef.pack,
      templateName: template ? nameOf(template, lang) : versionRef.template,
      packs: tree.packs.map((p) => ({
        id: p.id,
        name: nameOf(p, lang),
        current: p.id === versionRef.pack,
        empty:
          p.templates.length === 0
            ? "templates"
            : p.templates.every((t) => t.versions.length === 0)
              ? "versions"
              : null,
      })),
      templates: (pack?.templates ?? []).map((t) => ({
        id: t.id,
        name: nameOf(t, lang),
        current: t.id === versionRef.template,
        empty: t.versions.length === 0,
      })),
      versions: [...(template?.versions ?? [])].reverse().map((v) => ({
        version: v.version,
        current: v.version === versionRef.version,
        released: v.released,
        isDefault: v.version === template?.default_version,
        files: changedFilesOf(counts, v),
      })),
      mine,
      mineElsewhere: mine.filter((item) => !item.current),
      packDir: pack?.path.split("/")[0] ?? versionRef.pack,
      goPack: (id) => {
        if (id === versionRef.pack) return;
        const target = tree.packs.find((p) => p.id === id);
        if (target) go(refForPack(target, changed, lastOf));
      },
      goTemplate: (id) => {
        if (id === versionRef.template) return;
        const target = pack?.templates.find((t) => t.id === id);
        if (pack && target) go(refForTemplate(pack, target, changed, lastOf));
      },
      goVersion: (version) => {
        nav.go({ ref: { ...versionRef, version } });
      },
      goMine: (ref) => {
        nav.go({ ref });
      },
    };
  }, [changed, mineChanged, lang, nav, pack, template, tree, versionRef, wsId]);
};
