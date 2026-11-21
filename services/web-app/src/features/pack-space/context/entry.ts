import type { PackTree, PackVersionRef, SpaceTab } from "@entities/pack-studio";
import {
  changedFilesOf,
  countByVersion,
  pickDefaultVersion,
} from "../nav/pickDefaultVersion";
import type { SpacePlace } from "./memory";

// Вход в пространство без версии (`/w/:ws`, старые адреса без версии): куда открыть. Версию
// внутри шаблона выбирает `pickDefaultVersion` (срез S2): с моими изменениями, затем последняя
// посещённая, затем по умолчанию.

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
  /** Файлы, изменённые в пространстве (от папки паков): по ним находится версия с правками. */
  changed?: readonly string[] | undefined;
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

/** Версия, где человек был в этом шаблоне, если последнее место относится к нему. */
const lastIn = (
  pack: string,
  template: string,
  last: SpacePlace | null | undefined,
): string | null =>
  last?.ref.pack === pack && last.ref.template === template
    ? last.ref.version
    : null;

/**
 * Первая подходящая версия дерева (с необязательным сужением до шаблона). Без сужения шаблон с
 * моими изменениями идёт первым.
 */
const firstDefault = (
  tree: PackTree,
  only: { pack: string; template: string } | null | undefined,
  changed: readonly string[],
  last: SpacePlace | null | undefined,
): PackVersionRef | null => {
  const counts = countByVersion(changed);
  const found: { ref: PackVersionRef; edited: boolean }[] = [];
  for (const pack of tree.packs) {
    for (const template of pack.templates) {
      if (only && (only.pack !== pack.id || only.template !== template.id)) {
        continue;
      }
      const version = pickDefaultVersion(
        template,
        changed,
        lastIn(pack.id, template.id, last),
      );
      if (!version) continue;
      found.push({
        ref: { pack: pack.id, template: template.id, version },
        edited: template.versions.some((v) => changedFilesOf(counts, v) > 0),
      });
    }
  }
  return (found.find((item) => item.edited) ?? found[0])?.ref ?? null;
};

/** Порядок: версия из адреса, версия шаблона из адреса, последнее место, первая по умолчанию. */
export const resolveEntryPlace = (
  tree: PackTree,
  hints: EntryHints = {},
): EntryPlace | null => {
  const { ref, template, tab, last, changed = [] } = hints;
  const explicit =
    (ref && hasVersion(tree, ref) ? ref : null) ??
    (template ? firstDefault(tree, template, changed, last) : null);
  if (explicit) return { ref: explicit, tab: tab ?? "result", inputs: {} };
  if (last && hasVersion(tree, last.ref)) {
    return { ref: last.ref, tab: tab ?? last.tab, inputs: last.inputs };
  }
  const first = firstDefault(tree, null, changed, null);
  return first ? { ref: first, tab: tab ?? "result", inputs: {} } : null;
};
