// Контракт области «Содержимое» (docs/design/pack-studio-ux.md, 12.7): типы, которыми
// пользуются файлы-расширения S8b - S8d, и имена параметров адреса. Без зависимостей.

/** Разделы версии левой навигации (параметр `part`). */
export const CONTENT_PARTS = [
  "fields",
  "forms",
  "deadlines",
  "signatures",
  "languages",
  "rules",
  "files",
] as const;
export type ContentPart = (typeof CONTENT_PARTS)[number];

export const isContentPart = (value: string | null): value is ContentPart =>
  CONTENT_PARTS.some((part) => part === value);

/** Сегменты экрана документа (параметр `seg`): «Условия», «Текст», «Подписи». */
export const DOC_SEGMENTS = ["terms", "text", "signatures"] as const;
export type DocSegment = (typeof DOC_SEGMENTS)[number];

export const DEFAULT_SEGMENT: DocSegment = "text";

export const isDocSegment = (value: string | null): value is DocSegment =>
  DOC_SEGMENTS.some((segment) => segment === value);

/** Параметры адреса вкладки, у которых нет поля в `SpaceNavPatch` (идут через `extra`). */
export const CONTENT_QUERY = { segment: "seg", at: "at" } as const;

/** Файл папки документа: `path` полный (от папки паков), `bare` без языкового кода от `files/`. */
export type ContentDocFile = { path: string; bare: string; lang: string };

export type ContentDocument = {
  /** Имя папки `files/<id>`. */
  id: string;
  /** Название на языке интерфейса. */
  name: string;
  group: string | null;
  /** `<versionDir>/files/<id>/doc.yaml`. */
  manifestPath: string;
  files: ContentDocFile[];
  /** `bare` основного файла (`source_file` первого варианта), если манифест его называет. */
  mainFile: string | null;
};

/** Что получает сегмент экрана документа (`extend/segment-*.tsx`). */
export type DocumentSegmentProps = {
  workspaceId: string;
  /** Каталог версии от папки паков: `<пак>/templates/<шаблон>/versions/<версия>`. */
  versionDir: string;
  doc: ContentDocument;
  /** Значение `file` из адреса как есть (см. `resolveDocumentFile`). */
  file: string | null;
  /** Выпущенная версия или отказ сервера писать: не пишем, показываем «только чтение». */
  readOnly: boolean;
};

/** Что получает раздел версии (`extend/part-*.tsx`). */
export type ContentPartProps = {
  workspaceId: string;
  versionDir: string;
  part: ContentPart;
  /** JSON Pointer записи манифеста версии, к которой перешли (`at`). */
  at: string | null;
  file: string | null;
  readOnly: boolean;
};
