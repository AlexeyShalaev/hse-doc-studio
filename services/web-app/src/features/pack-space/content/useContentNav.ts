import { useCallback, useMemo, type MouseEvent } from "react";
import { useTranslation } from "react-i18next";
import { useSpaceNav } from "../context/useSpaceNav";
import type { ContentPart, DocSegment } from "./contract";
import { confirmContentLeave } from "./contentGuard";
import { contentDocumentPatch, contentPartPatch } from "./link";
import { patchForFile } from "./route";
import { useContentData } from "./useContentData";

export type ContentNav = {
  documentHref: (
    docId: string,
    options?: { segment?: DocSegment; file?: string | null },
  ) => string;
  partHref: (
    part: ContentPart,
    options?: { file?: string | null; at?: string | null },
  ) => string;
  toDocument: (
    docId: string,
    options?: { segment?: DocSegment; file?: string | null },
  ) => void;
  toPart: (
    part: ContentPart,
    options?: { file?: string | null; at?: string | null },
  ) => void;
  /** Открыть файл по пути: файл документа в его «Тексте», остальное в «Все файлы». */
  toFile: (path: string) => void;
  /** Для `onClick` ссылки: спрашивает про несохранённое и отменяет переход при отказе. */
  guardClick: (event: MouseEvent) => void;
};

/**
 * Переходы внутри «Содержимого» (обёртка над `useSpaceNav`). Все они идут заменой записи
 * истории: документы листают, а не уходят «назад» по одному. Спрашивают про несохранённое.
 */
export const useContentNav = (): ContentNav => {
  const { t } = useTranslation("packSpace");
  const nav = useSpaceNav();
  const { versionDir, docs } = useContentData();
  const leave = useCallback(() => confirmContentLeave(t("content.leave")), [t]);
  return useMemo<ContentNav>(
    () => ({
      documentHref: (docId, options) =>
        nav.href(contentDocumentPatch(docId, options)),
      partHref: (part, options) => nav.href(contentPartPatch(part, options)),
      toDocument: (docId, options) => {
        if (leave()) nav.go(contentDocumentPatch(docId, options));
      },
      toPart: (part, options) => {
        if (leave()) nav.go(contentPartPatch(part, options));
      },
      toFile: (path) => {
        const ids = docs.map((doc) => doc.id);
        if (leave()) nav.go(patchForFile(path, versionDir, ids));
      },
      guardClick: (event) => {
        // Переход в новой вкладке или окне страницу не покидает.
        if (
          event.metaKey ||
          event.ctrlKey ||
          event.shiftKey ||
          event.button !== 0
        ) {
          return;
        }
        if (!leave()) event.preventDefault();
      },
    }),
    [nav, leave, docs, versionDir],
  );
};
