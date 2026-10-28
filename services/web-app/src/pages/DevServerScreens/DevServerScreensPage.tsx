import { useMemo } from "react";
import type { GallerySection } from "@shared/lib/stateGallery";
import { buildServerSections } from "./serverSections";
import { StateGalleryPage, type GalleryDemo } from "@shared/ui/StateGallery";

// Метка для проверки сборки: в рабочий бандл этой строки попасть не должно.
export const DEV_SERVER_SCREENS_MARKER = "hse-dev-server-screens-gallery";

export type DevServerScreensPageProps = {
  /** Демо-API: нужен живым записям. Без него они только описаны. */
  demo?: GalleryDemo | null;
  /** Разделы для проверки; по умолчанию собираются из экранов серверного режима. */
  sections?: GallerySection[];
  /** Разделы страниц-соседей: страницы друг друга не импортируют, их передаёт приложение. */
  extraSections?: GallerySection[];
};

/**
 * Галерея экранов серверного режима (только в разработке, адрес
 * /dev/server-screens): все состояния на демо-данных, с переключением темы и
 * языка. Каркас общий с галереей git-синхронизации.
 */
export const DevServerScreensPage = ({
  demo = null,
  sections: sectionsProp,
  extraSections,
}: DevServerScreensPageProps) => {
  const sections = useMemo(
    () => [
      ...(sectionsProp ?? buildServerSections()),
      ...(extraSections ?? []),
    ],
    [sectionsProp, extraSections],
  );
  return (
    <StateGalleryPage
      title="Экраны серверного режима"
      basePath="/dev/server-screens"
      marker={DEV_SERVER_SCREENS_MARKER}
      demo={demo}
      sections={sections}
    />
  );
};
