import type { SpaceNavPatch } from "../context/nav";
import {
  CONTENT_QUERY,
  DEFAULT_SEGMENT,
  isContentPart,
  isDocSegment,
  type ContentPart,
  type DocSegment,
} from "./contract";
import { contentDocumentPatch, contentPartPatch } from "./link";

// Что открыто во вкладке «Содержимое»: решается только по адресу и списку документов.

export type ContentRoute =
  | {
      kind: "document";
      docId: string;
      segment: DocSegment;
      file: string | null;
    }
  | { kind: "part"; part: ContentPart; file: string | null; at: string | null }
  /** Адрес пуст: вкладка выбирает документ сама (последний или первый). */
  | { kind: "none" };

/** Раздел формы версии по указателю записи манифеста (как `sectionOfPointer` прежней формы). */
export const partOfPointer = (pointer: string | null): ContentPart | null => {
  switch (pointer?.split("/")[1]) {
    case "meta_fields":
    case "meta_groups":
      return "fields";
    case "forms":
      return "forms";
    case "langs":
      return "languages";
    case "pack_submission":
      return "deadlines";
    case "signatures":
      return "signatures";
    case "checks_version":
      return "rules";
    default:
      return null;
  }
};

/** Путь внутри `files/` версии (без каталога версии и без самого `files/`); иначе `null`. */
export const insideFiles = (
  path: string,
  versionDir: string,
): string | null => {
  const prefix = `${versionDir}/files/`;
  if (path.startsWith(prefix)) return path.slice(prefix.length);
  return null;
};

/**
 * Разбор адреса. `docIds` это документы версии: файл внутри `files/<id>/` ведёт на этот документ,
 * а общие файлы (`files/common/...`) и прочее открываются в «Все файлы». Старый `?file=` (из
 * `legacyToSpace`) попадает сюда же: `doc.yaml` это «Условия», `version.yaml` с `at` ведёт в раздел.
 */
export const readContentRoute = (
  search: string,
  versionDir: string,
  docIds: readonly string[],
): ContentRoute => {
  const params = new URLSearchParams(search);
  const part = params.get("part");
  const doc = params.get("doc");
  const file = params.get("file");
  const at = params.get(CONTENT_QUERY.at);
  const segment = params.get(CONTENT_QUERY.segment);
  if (isContentPart(part)) return { kind: "part", part, file, at };
  if (doc !== null && doc !== "") {
    return {
      kind: "document",
      docId: doc,
      segment: isDocSegment(segment) ? segment : DEFAULT_SEGMENT,
      file,
    };
  }
  if (file === null || file === "") return { kind: "none" };
  const inFiles = insideFiles(file, versionDir);
  const owner = inFiles?.split("/")[0];
  if (inFiles !== null && owner !== undefined && docIds.includes(owner)) {
    const isManifest = inFiles === `${owner}/doc.yaml`;
    return {
      kind: "document",
      docId: owner,
      segment: isManifest ? "terms" : "text",
      file: isManifest ? null : file,
    };
  }
  if (file === `${versionDir}/version.yaml`) {
    const byPointer = partOfPointer(at);
    if (byPointer) return { kind: "part", part: byPointer, file: null, at };
  }
  return { kind: "part", part: "files", file, at };
};

/**
 * Куда вести путь файла (из «Проблем», из формы): файл документа это его «Текст» (манифест
 * документа его «Условия»), всё остальное «Все файлы».
 */
export const patchForFile = (
  path: string,
  versionDir: string,
  docIds: readonly string[],
): SpaceNavPatch => {
  const inFiles = insideFiles(path, versionDir);
  const owner = inFiles?.split("/")[0];
  if (inFiles !== null && owner !== undefined && docIds.includes(owner)) {
    return inFiles === `${owner}/doc.yaml`
      ? contentDocumentPatch(owner, { segment: "terms" })
      : contentDocumentPatch(owner, { segment: "text", file: path });
  }
  return contentPartPatch("files", { file: path });
};
