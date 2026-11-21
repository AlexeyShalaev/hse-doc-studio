import { isTextPath, type PackVersionModel } from "@entities/pack-studio";
import { pickLocalized } from "@shared/lib";
import type { ContentDocFile, ContentDocument } from "./contract";

// Документы версии для навигации и экрана документа: из модели версии (ответ сервера), без
// запросов. Модель отдаёт файлы папки документа от `files/` версии; здесь пути становятся полными.

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

const strings = (value: unknown): Record<string, string> =>
  isRecord(value)
    ? Object.fromEntries(
        Object.entries(value).filter(
          (entry): entry is [string, string] => typeof entry[1] === "string",
        ),
      )
    : {};

/** Название документа на языке интерфейса; без названия id. */
const nameOf = (data: unknown, id: string, lang: string): string => {
  const name = isRecord(data) ? data.name : undefined;
  if (typeof name === "string") return name;
  return pickLocalized(strings(name), lang, id);
};

/** `source_file` документа: у записи v2 в первом варианте, у v1 прямо в записи. */
const mainFileOf = (data: unknown): string | null => {
  if (!isRecord(data)) return null;
  const variants: unknown[] = Array.isArray(data.variants) ? data.variants : [];
  for (const variant of [...variants, data]) {
    if (isRecord(variant) && typeof variant.source_file === "string") {
      return variant.source_file;
    }
  }
  return null;
};

export const toContentDocuments = (
  model: PackVersionModel,
  versionDir: string,
  lang: string,
): ContentDocument[] =>
  model.documents.map((doc) => {
    const data = doc.manifest?.data ?? doc.data;
    return {
      id: doc.id,
      name: nameOf(data, doc.id, lang),
      group:
        isRecord(data) && typeof data.group === "string" ? data.group : null,
      manifestPath:
        doc.manifest?.path ?? `${versionDir}/files/${doc.id}/doc.yaml`,
      files: doc.files.map((file) => ({
        path: `${versionDir}/files/${file.path}`,
        bare: file.bare,
        lang: file.lang,
      })),
      mainFile: mainFileOf(data),
    };
  });

/** Редакция на нужном языке: свой язык, затем файл для всех языков, затем первая имеющаяся. */
const pickEdition = (
  files: readonly ContentDocFile[],
  lang: string,
): ContentDocFile | null =>
  files.find((file) => file.lang === lang) ??
  files.find((file) => file.lang === "") ??
  files[0] ??
  null;

/** Файлы документа, которые открываются как текст (картинки, шрифты, офисные файлы нет). */
export const textFilesOf = (doc: ContentDocument): ContentDocFile[] =>
  doc.files.filter((file) => isTextPath(file.path));

/**
 * Какой файл документа открыть. `file` из адреса может быть полным путём, путём от `files/`
 * версии (с языковым суффиксом или без, как `source_file` из «Результата») или пустым: тогда
 * основной файл документа, затем первый текстовый. Язык редакции берётся из `lang`, если
 * `file` его не назвал.
 */
export const resolveDocumentFile = (
  doc: ContentDocument,
  file: string | null,
  lang: string,
  versionDir: string,
): ContentDocFile | null => {
  const texts = textFilesOf(doc);
  if (file) {
    const wanted = file.startsWith(`${versionDir}/files/`)
      ? file.slice(`${versionDir}/files/`.length)
      : file;
    const exact = texts.find(
      (item) => item.path === `${versionDir}/files/${wanted}`,
    );
    if (exact) return exact;
    const sameBare = texts.filter((item) => item.bare === wanted);
    if (sameBare.length > 0) return pickEdition(sameBare, lang);
  }
  if (doc.mainFile) {
    const main = texts.filter((item) => item.bare === doc.mainFile);
    if (main.length > 0) return pickEdition(main, lang);
  }
  return pickEdition(texts, lang);
};

/** Подпись файла в переключателе: имя без языкового кода и язык редакции. */
export const fileLabel = (file: ContentDocFile): string => {
  const name = file.bare.split("/").pop() ?? file.bare;
  return file.lang ? `${name} · ${file.lang}` : name;
};
