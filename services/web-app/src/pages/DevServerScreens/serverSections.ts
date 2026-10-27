import { getSignInGallery } from "@features/sign-in";
import { getSessionGallery } from "@entities/session";
import type { GallerySection } from "@shared/lib/stateGallery";

/** Разделы галереи. Каждый экран серверного режима добавляет сюда свою группу. */
export const buildServerSections = (): GallerySection[] => [
  { id: "session", title: "Сессия и bootstrap", groups: getSessionGallery() },
  { id: "sign-in", title: "Вход", groups: getSignInGallery() },
];
