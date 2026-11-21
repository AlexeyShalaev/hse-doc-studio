import type {
  PackTree,
  PackTreeTemplate,
  PackVersionRef,
  SpaceTab,
} from "@entities/pack-studio";
import type { SpacePlace } from "./memory";

// Вход в пространство без версии (`/w/:ws`, старые адреса без версии): куда открыть.
// Срез S2 заменяет выбор на `pickDefaultVersion` (версия с моими изменениями, затем последняя
// посещённая, затем умолчание); контракт тот же: дерево и подсказки на входе, место на выходе.

export type EntryPlace = {
  ref: PackVersionRef;
  tab: SpaceTab;
  /** Условия студента, которые вернулись из памяти (только когда вход без своих подсказок). */
  inputs: Record<string, string>;
};

export type EntryHints = {
  ref?: PackVersionRef | null | undefined;
  template?: { pack: string; template: string } | null | undefined;
  tab?: SpaceTab | null | undefined;
  last?: SpacePlace | null | undefined;
};

export const hasVersion = (tree: PackTree, ref: PackVersionRef): boolean =>
  tree.packs.some(
    (pack) =>
      pack.id === ref.pack &&
      pack.templates.some(
        (template) =>
          template.id === ref.template &&
          template.versions.some((v) => v.version === ref.version),
      ),
  );

const defaultOf = (
  pack: string,
  template: PackTreeTemplate,
): PackVersionRef | null => {
  const chosen =
    template.versions.find((v) => v.version === template.default_version) ??
    template.versions[template.versions.length - 1];
  return chosen
    ? { pack, template: template.id, version: chosen.version }
    : null;
};

/** Первая версия по умолчанию в дереве (с необязательным сужением до шаблона). */
const firstDefault = (
  tree: PackTree,
  only?: { pack: string; template: string } | null,
): PackVersionRef | null => {
  for (const pack of tree.packs) {
    for (const template of pack.templates) {
      if (only && (only.pack !== pack.id || only.template !== template.id)) {
        continue;
      }
      const ref = defaultOf(pack.id, template);
      if (ref) return ref;
    }
  }
  return null;
};

/** Порядок: версия из адреса, версия шаблона из адреса, последнее место, первая по умолчанию. */
export const resolveEntryPlace = (
  tree: PackTree,
  hints: EntryHints = {},
): EntryPlace | null => {
  const { ref, template, tab, last } = hints;
  const explicit =
    (ref && hasVersion(tree, ref) ? ref : null) ??
    (template ? firstDefault(tree, template) : null);
  if (explicit) return { ref: explicit, tab: tab ?? "result", inputs: {} };
  if (last && hasVersion(tree, last.ref)) {
    return { ref: last.ref, tab: tab ?? last.tab, inputs: last.inputs };
  }
  const first = firstDefault(tree);
  return first ? { ref: first, tab: tab ?? "result", inputs: {} } : null;
};
