import type { PackVersionRef } from "@entities/pack-studio";

/** Ключ версии `пак/шаблон/версия`: по нему панель «Изменения» находит имена документов версии. */
export const versionKeyOf = (ref: PackVersionRef): string =>
  `${ref.pack}/${ref.template}/${ref.version}`;
