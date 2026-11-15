import type {
  PackScaffoldOptions,
  PackScaffoldSource,
} from "@entities/pack-studio";

// Те же правила, что на сервере (core/pack_studio/scaffold.py): id это имя
// папки и ключ манифеста, только строчные, чтобы на macOS и Windows не было
// двух папок, которые на диске одна.
const PACK_ID = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
const TEMPLATE_ID = /^[a-z0-9]+(?:[_-][a-z0-9]+)*$/;
const ID_MAX = 64;

export const isPackId = (value: string): boolean =>
  value.length <= ID_MAX && PACK_ID.test(value);

export const isTemplateId = (value: string): boolean =>
  value.length <= ID_MAX && TEMPLATE_ID.test(value);

export const isPackIdTaken = (
  options: PackScaffoldOptions | undefined,
  value: string,
): boolean => options?.taken_packs.includes(value.toLowerCase()) ?? false;

export type SourceChoice = {
  key: string;
  source: PackScaffoldSource;
  /** Подпись пака и шаблона без версии: по ней строится подпись варианта. */
  title: string;
  isDefault: boolean;
};

const keyOf = (s: PackScaffoldSource): string =>
  JSON.stringify([s.origin, s.pack, s.template, s.version]);

/**
 * Версии, которые можно скопировать: сначала паки пространства, затем каталог
 * Студии, в шаблоне новые версии первыми (так их отдаёт сервер).
 */
export const sourceChoices = (
  options: PackScaffoldOptions | undefined,
): SourceChoice[] =>
  (options?.sources ?? []).flatMap((pack) =>
    pack.templates.flatMap((template) =>
      template.versions.map((version) => {
        const source: PackScaffoldSource = {
          origin: pack.origin,
          pack: pack.pack,
          template: template.template,
          version: version.version,
        };
        return {
          key: keyOf(source),
          source,
          title: `${pack.pack} / ${template.template}`,
          isDefault: version.default,
        };
      }),
    ),
  );

/** Вариант по умолчанию: версия по умолчанию первого шаблона, иначе первая. */
export const defaultChoice = (
  choices: readonly SourceChoice[],
): SourceChoice | undefined =>
  choices.find((choice) => choice.isDefault) ?? choices[0];

export type LocalizedDraft = { ru: string; en: string };

export const hasName = (name: LocalizedDraft): boolean =>
  name.ru.trim().length > 0 || name.en.trim().length > 0;

export const localized = (name: LocalizedDraft) => ({
  ru: name.ru.trim(),
  en: name.en.trim(),
});
