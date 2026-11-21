import { useMemo } from "react";
import { useSpace } from "../context/SpaceContext";
import { readUi } from "../context/memory";
import { useSpacePhone } from "../shell/phoneContext";
import { DEFAULT_SEGMENT, isDocSegment } from "./contract";
import { readContentRoute, type ContentRoute } from "./route";
import type { ContentData } from "./useContentData";

/** Память вкладки: последний документ и сегмент (на пространство). */
export const MEMORY_DOC = "content.doc";
export const MEMORY_SEGMENT = "content.seg";

/**
 * Что открыто: по адресу, а пустой адрес это последний документ (память) или первый. Адрес при
 * этом не переписывается: ссылку без `doc` каждый открывает на своём последнем документе. На
 * телефоне пустой адрес это страница-список «Что редактируем» (`none`): правка документа или
 * раздела следующая страница с кнопкой «назад» (5.8).
 */
export const useContentRoute = (data: ContentData): ContentRoute => {
  const { workspace, location } = useSpace();
  const phone = useSpacePhone();
  const ids = useMemo(() => data.docs.map((doc) => doc.id), [data.docs]);
  const route = readContentRoute(location.search, data.versionDir, ids);
  if (route.kind !== "none" || phone) return route;
  const remembered = readUi(workspace.id, MEMORY_DOC);
  const docId =
    typeof remembered === "string" && ids.includes(remembered)
      ? remembered
      : ids[0];
  if (docId === undefined) return route;
  const seg = readUi(workspace.id, MEMORY_SEGMENT);
  return {
    kind: "document",
    docId,
    segment:
      typeof seg === "string" && isDocSegment(seg) ? seg : DEFAULT_SEGMENT,
    file: null,
  };
};
