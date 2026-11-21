import type { SpaceNavPatch } from "../context/nav";
import {
  CONTENT_QUERY,
  DEFAULT_SEGMENT,
  type ContentPart,
  type DocSegment,
} from "./contract";

// Ссылки на вкладку «Содержимое» для других областей (`result`: «Текст документа», `check`:
// «Исправить»). Только данные, без React и тяжёлых импортов: файл безопасно тянуть из своего
// слота. Применять через `useSpaceNav().go(...)` или `.href(...)`.

/** Экран документа. `file`: `source_file` из «Результата» или путь файла (см. 12.7). */
export const contentDocumentPatch = (
  docId: string,
  options: { segment?: DocSegment; file?: string | null } = {},
): SpaceNavPatch => {
  const segment = options.segment ?? DEFAULT_SEGMENT;
  return {
    tab: "content",
    doc: docId,
    part: null,
    file: options.file ?? null,
    extra: {
      [CONTENT_QUERY.segment]: segment === DEFAULT_SEGMENT ? null : segment,
      [CONTENT_QUERY.at]: null,
    },
  };
};

/** Раздел версии: поля, анкеты, сроки, подписи, языки, правила, все файлы. */
export const contentPartPatch = (
  part: ContentPart,
  options: { file?: string | null; at?: string | null } = {},
): SpaceNavPatch => ({
  tab: "content",
  doc: null,
  part,
  file: options.file ?? null,
  extra: {
    [CONTENT_QUERY.segment]: null,
    [CONTENT_QUERY.at]: options.at ?? null,
  },
});
