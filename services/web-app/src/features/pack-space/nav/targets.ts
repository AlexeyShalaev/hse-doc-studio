import type {
  PackTreePack,
  PackTreeTemplate,
  PackVersionRef,
} from "@entities/pack-studio";
import {
  changedFilesOf,
  countByVersion,
  pickDefaultVersion,
} from "./pickDefaultVersion";

// Куда переходит смена пака или шаблона в крошках: всегда на версию, выбранную по общему порядку
// (`pickDefaultVersion`), а не на «версию по умолчанию вслепую»: работа не теряется.

/** Версия, где человек был в прошлый раз, по паку и шаблону. */
export type LastVersionOf = (pack: string, template: string) => string | null;

export const refForTemplate = (
  pack: PackTreePack,
  template: PackTreeTemplate,
  changedPaths: readonly string[],
  lastVersionOf: LastVersionOf,
): PackVersionRef | null => {
  const version = pickDefaultVersion(
    template,
    changedPaths,
    lastVersionOf(pack.id, template.id),
  );
  return version ? { pack: pack.id, template: template.id, version } : null;
};

/** Шаблон пака, в который перейти: с моими изменениями, иначе первый, у которого есть версии. */
export const refForPack = (
  pack: PackTreePack,
  changedPaths: readonly string[],
  lastVersionOf: LastVersionOf,
): PackVersionRef | null => {
  const counts = countByVersion(changedPaths);
  const withChanges = pack.templates.find((template) =>
    template.versions.some((v) => changedFilesOf(counts, v) > 0),
  );
  const template =
    withChanges ?? pack.templates.find((item) => item.versions.length > 0);
  return template
    ? refForTemplate(pack, template, changedPaths, lastVersionOf)
    : null;
};
