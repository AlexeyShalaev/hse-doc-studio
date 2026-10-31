import { getBuildStatesGallery } from "@features/build-states";
import { getAdminInstallGallery } from "@features/admin-install";
import { getAdminOpsGallery } from "@features/admin-ops";
import { getAdminOrgsGallery } from "@features/admin-orgs";
import { getAdminAuthSettingsGallery } from "@features/admin-auth-settings";
import { getAccountSettingsGallery } from "@features/account-settings";
import { getMyOrganizationsGallery } from "@features/my-organizations";
import { getMyRunnersGallery } from "@features/my-runners";
import { getRemoteRunnerGallery } from "@features/remote-runner";
import { getRelayGallery } from "@features/agent-chat";
import { getAiProviderRelayGallery } from "@features/manage-ai-provider";
import { getProjectAccessGallery } from "@features/project-access";
import { getShareLinksGallery } from "@features/share-links";
import { getGuestSessionGallery } from "@features/guest-session";
import { getOrgSharingGallery } from "@features/my-organizations";
import { getAdminSharingGallery } from "@features/admin-install";
import { getProjectImportGallery } from "@features/project-import";
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
  {
    id: "admin-orgs",
    title: "Админка: организации",
    groups: getAdminOrgsGallery(),
  },
  {
    id: "my-orgs",
    title: "Настройки: организации участника",
    groups: getMyOrganizationsGallery(),
  },
  {
    id: "my-runners",
    title: "Настройки: мои раннеры",
    groups: getMyRunnersGallery(),
  },
  {
    id: "remote-runner",
    title: "Локальная Студия: облачные сборки",
    groups: getRemoteRunnerGallery(),
  },
  {
    id: "ai-relay",
    title: "ИИ через свой раннер",
    groups: [...getRelayGallery(), ...getAiProviderRelayGallery()],
  },
  {
    id: "project-access",
    title: "Проект: доступ",
    groups: getProjectAccessGallery(),
  },
  {
    id: "share-links",
    title: "Проект: доступ по ссылке",
    groups: getShareLinksGallery(),
  },
  {
    id: "guest",
    title: "Гость по ссылке",
    groups: getGuestSessionGallery(),
  },
  {
    id: "sharing-policy",
    title: "Политика общего доступа",
    groups: [...getOrgSharingGallery(), ...getAdminSharingGallery()],
  },
  {
    id: "project-import",
    title: "Импорт проекта из локальной Студии",
    groups: getProjectImportGallery(),
  },
  {
    id: "build-states",
    title: "Сборка и редактор: очередь, раннер, занято",
    groups: getBuildStatesGallery(),
  },
  {
    id: "admin-ops",
    title: "Админка: раннеры, очередь, квоты, сервисы",
    groups: getAdminOpsGallery(),
  },
  {
    id: "admin-install",
    title: "Админка: установка, ключи подписи, общие провайдеры",
    groups: getAdminInstallGallery(),
  },
  { id: "shell", title: "Оболочка", groups: getAccountMenuGallery() },
  { id: "admin-kit", title: "Примитивы админки", groups: getAdminKitGallery() },
];
