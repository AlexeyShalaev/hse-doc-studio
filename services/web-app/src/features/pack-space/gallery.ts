import type { GalleryEntry, GalleryGroup } from "@shared/lib/stateGallery";

// Галерея нового интерфейса (`/dev/server-screens`, раздел «Студия шаблонов»). Общего списка нет:
// каждая область кладёт записи в `<область>/gallery.<область>.tsx` (`export const galleryEntries`),
// отсюда они собираются глобом, поэтому срезы не конфликтуют. Подключает только dev-маршрут,
// из `index.ts` файл не экспортируется.
const modules = import.meta.glob<{ galleryEntries: GalleryEntry[] }>(
  "./*/gallery.*.tsx",
  { eager: true },
);

export const getPackSpaceGallery = (): GalleryGroup[] => [
  {
    id: "pack-space",
    title: "Студия шаблонов: новый интерфейс",
    description:
      "Каркас и области нового вида Студии (`?ux=2`): светлая и тёмная темы, десктоп, планшет, телефон.",
    entries: Object.keys(modules)
      .sort()
      .flatMap((path) => modules[path]?.galleryEntries ?? []),
  },
];
