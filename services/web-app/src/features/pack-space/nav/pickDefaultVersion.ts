import {
  versionDirOf,
  type PackTree,
  type PackTreeTemplate,
  type PackVersionRef,
} from "@entities/pack-studio";

// Какую версию открыть, когда место выбрано не по версии: вход в пространство без версии, смена
// пака или шаблона (pack-studio-ux.md, 9.3, срез S2). Порядок один и тот же везде:
//   1. версия, где у человека есть изменения (работа не теряется при смене пака или шаблона);
//   2. версия, где он был в прошлый раз;
//   3. версия по умолчанию шаблона (или самая новая, если умолчания нет).

/** Сколько файлов изменено в каждой версии: ключ это каталог версии в нижнем регистре. */
export type ChangedVersions = ReadonlyMap<string, number>;

/** Изменённые пути (от папки паков) по версиям. Пути вне версий (манифест пака) не считаются. */
export const countByVersion = (
  changedPaths: readonly string[],
): ChangedVersions => {
  const counts = new Map<string, number>();
  for (const path of changedPaths) {
    const dir = versionDirOf(path)?.toLowerCase();
    if (dir) counts.set(dir, (counts.get(dir) ?? 0) + 1);
  }
  return counts;
};

export const changedFilesOf = (
  counts: ChangedVersions,
  version: { path: string },
): number => counts.get(version.path.toLowerCase()) ?? 0;

/**
 * Версия шаблона, которую открыть. `changedPaths` это изменённые файлы пространства, `last` это
 * версия этого шаблона, где человек был в прошлый раз. `null`: у шаблона нет версий.
 */
export const pickDefaultVersion = (
  template: PackTreeTemplate,
  changedPaths: readonly string[],
  last: string | null,
): string | null => {
  const { versions } = template;
  if (versions.length === 0) return null;
  const counts = countByVersion(changedPaths);
  const changed = versions.filter((v) => changedFilesOf(counts, v) > 0);
  const remembered = versions.find((v) => v.version === last);
  if (changed.length > 0) {
    // Несколько версий с изменениями (редко): та, где были, иначе самая новая.
    return (
      (changed.find((v) => v.version === last) ?? changed[changed.length - 1])
        ?.version ?? null
    );
  }
  if (remembered) return remembered.version;
  const preferred = versions.find(
    (v) => v.version === template.default_version,
  );
  return (preferred ?? versions[versions.length - 1])?.version ?? null;
};

/** Версия с моими изменениями: то, что показывают «Мои правки» и «К моему черновику». */
export type MyChange = { ref: PackVersionRef; files: number };

/** Версии дерева, где есть изменения, в порядке дерева. */
export const myChanges = (
  tree: PackTree,
  changedPaths: readonly string[],
): MyChange[] => {
  const counts = countByVersion(changedPaths);
  const found: MyChange[] = [];
  for (const pack of tree.packs) {
    for (const template of pack.templates) {
      for (const version of template.versions) {
        const files = changedFilesOf(counts, version);
        if (files > 0) {
          found.push({
            ref: {
              pack: pack.id,
              template: template.id,
              version: version.version,
            },
            files,
          });
        }
      }
    }
  }
  return found;
};
