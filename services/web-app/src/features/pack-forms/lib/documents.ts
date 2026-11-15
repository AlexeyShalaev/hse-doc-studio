import type { PackDocFile, PackModelDocument } from "@entities/pack-studio";
import { asRecord, asStrings } from "./raw";

// Документы версии (ростер `documents`, `files/<id>/doc.yaml`): template-studio.md, 5.3.

/** Группы навигации, у которых в Студии есть подпись (остальные идут в «Прочее»). */
export const KNOWN_DOC_GROUPS = [
  "topic",
  "espd",
  "report",
  "work",
  "pdp",
  "pres",
  "nda",
];

/** Ключ подписи группы в словаре рабочего места (те же, что у панели документов). */
export const docGroupLabelKey = (group: string): string =>
  KNOWN_DOC_GROUPS.includes(group)
    ? `workbench:documents.group${group.charAt(0).toUpperCase()}${group.slice(1)}`
    : "workbench:documents.groupOther";

export const ENGINES = ["xelatex", "lualatex", "pdflatex", "none"];
export const SCOPES = ["shared", "personal"];
export const STAFFING = ["solo", "team"];

/** Языки версии (`langs`); первый это язык по умолчанию. Без ключа это ru. */
export const versionLangs = (manifest: unknown): string[] => {
  const langs = asStrings(asRecord(manifest).langs);
  return langs.length ? langs : ["ru"];
};

export const LANG_CODE = /^[a-z]{2}(?:-[a-z]{2})?$/;

/** Документ из папки (`files/<id>/doc.yaml`), а не запись v1 прямо в ростере. */
export const isBundle = (doc: PackModelDocument): boolean =>
  doc.manifest !== null;

export type FileGroup = {
  /** Путь без языкового кода от `files/` версии. */
  bare: string;
  /** Код языка в путь файла; "" это файл для всех языков. */
  byLang: Record<string, string>;
};

/** Файлы документа по группам «один файл в разных языках», по алфавиту. */
export const fileGroups = (files: PackDocFile[]): FileGroup[] => {
  const groups = new Map<string, FileGroup>();
  for (const file of files) {
    const group = groups.get(file.bare) ?? { bare: file.bare, byLang: {} };
    group.byLang[file.lang] = file.path;
    groups.set(file.bare, group);
  }
  return [...groups.values()].sort((a, b) => a.bare.localeCompare(b.bare));
};

/** Файл, который переводят: исходники (а не картинки и шаблоны Jinja). */
export const isSource = (bare: string): boolean =>
  /\.(tex|md|html|txt|pptx|docx)$/i.test(bare);

/** Можно ли перевести документ на язык: есть редакция языка по умолчанию без этого перевода. */
export const translatable = (
  doc: PackModelDocument,
  lang: string,
  defaultLang: string,
): boolean =>
  fileGroups(doc.files).some(
    (g) => defaultLang in g.byLang && !(lang in g.byLang),
  );
