import type { TFunction } from "i18next";
import type { ChangeKind } from "./describeChanges";

/** Слова строки списка: «Документ: текст», «Описание версии». */
export const itemLabel = (
  t: TFunction,
  kind: ChangeKind,
  doc: string | null,
  names: Readonly<Record<string, string>>,
): string =>
  t(`changes.what.item.${kind}`, { doc: doc ? (names[doc] ?? doc) : "" });
