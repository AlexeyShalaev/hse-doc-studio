import { useMemo } from "react";
import type { GallerySection } from "@shared/lib/stateGallery";
import { StateGalleryPage, type GalleryDemo } from "@shared/ui/StateGallery";
import { buildGallerySections } from "./gallerySections";

// Метка для проверки сборки: в рабочий бандл этой строки попасть не должно.
export const DEV_SYNC_STATES_MARKER = "hse-dev-sync-states-gallery";

export type DevSyncStatesPageProps = {
  /** Демо-API: нужен живым записям. Без него они только описаны. */
  demo?: GalleryDemo | null;
  /** Разделы для проверки; по умолчанию собираются из всех фич. */
  sections?: GallerySection[];
};

/**
 * Галерея состояний git-синхронизации (только в разработке, адрес
 * /dev/sync-states): каждое состояние кнопки, панелей, шагов подключения,
 * клонирования, конфликтов и обмена файлом на готовых данных, с переключением
 * темы и языка. Каркас общий с галереей серверных экранов.
 */
export const DevSyncStatesPage = ({
  demo = null,
  sections: sectionsProp,
}: DevSyncStatesPageProps) => {
  const sections = useMemo(
    () => sectionsProp ?? buildGallerySections(),
    [sectionsProp],
  );
  return (
    <StateGalleryPage
      title="Состояния синхронизации"
      basePath="/dev/sync-states"
      marker={DEV_SYNC_STATES_MARKER}
      demo={demo}
      sections={sections}
    />
  );
};
