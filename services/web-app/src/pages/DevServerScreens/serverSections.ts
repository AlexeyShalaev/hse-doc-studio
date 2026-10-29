import { getAdminAuthSettingsGallery } from "@features/admin-auth-settings";
import { getAccountSettingsGallery } from "@features/account-settings";
import { getAccountMenuGallery } from "@features/account-menu";
import { getRecoveryGallery } from "@features/account-recovery";
import { getServerSetupGallery } from "@features/server-setup";
import { getSignInGallery } from "@features/sign-in";
import { getSignUpGallery } from "@features/sign-up";
import { getSessionGallery } from "@entities/session";
import type { GallerySection } from "@shared/lib/stateGallery";
import { getAdminKitGallery } from "@shared/ui/AdminKitGallery";

/** Разделы галереи. Каждый экран серверного режима добавляет сюда свою группу. */
export const buildServerSections = (): GallerySection[] => [
  { id: "session", title: "Сессия и bootstrap", groups: getSessionGallery() },
  {
    id: "first-run",
    title: "Мастер первого запуска",
    groups: getServerSetupGallery(),
  },
  { id: "sign-in", title: "Вход", groups: getSignInGallery() },
  { id: "sign-up", title: "Регистрация", groups: getSignUpGallery() },
  {
    id: "recovery",
    title: "Пароль и подтверждение почты",
    groups: getRecoveryGallery(),
  },
  {
    id: "account",
    title: "Настройки аккаунта",
    groups: getAccountSettingsGallery(),
  },
  {
    id: "admin-settings",
    title: "Админка: настройки входа",
    groups: getAdminAuthSettingsGallery(),
  },
  { id: "shell", title: "Оболочка", groups: getAccountMenuGallery() },
  { id: "admin-kit", title: "Примитивы админки", groups: getAdminKitGallery() },
];
