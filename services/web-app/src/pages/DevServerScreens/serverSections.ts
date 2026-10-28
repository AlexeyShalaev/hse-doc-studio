import { getAccountMenuGallery } from "@features/account-menu";
import { getRecoveryGallery } from "@features/account-recovery";
import { getSignInGallery } from "@features/sign-in";
import { getSignUpGallery } from "@features/sign-up";
import { getSessionGallery } from "@entities/session";
import type { GallerySection } from "@shared/lib/stateGallery";

/** Разделы галереи. Каждый экран серверного режима добавляет сюда свою группу. */
export const buildServerSections = (): GallerySection[] => [
  { id: "session", title: "Сессия и bootstrap", groups: getSessionGallery() },
  { id: "sign-in", title: "Вход", groups: getSignInGallery() },
  { id: "sign-up", title: "Регистрация", groups: getSignUpGallery() },
  {
    id: "recovery",
    title: "Пароль и подтверждение почты",
    groups: getRecoveryGallery(),
  },
  { id: "shell", title: "Оболочка", groups: getAccountMenuGallery() },
];
