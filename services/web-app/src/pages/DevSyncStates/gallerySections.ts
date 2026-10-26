import { getProfileGallery } from "@features/author-profile";
import { getConflictsGallery } from "@features/git-conflicts";
import { getExchangeGallery } from "@features/git-exchange";
import {
  getRemoteLiveGallery,
  getRemoteStaticGallery,
} from "@features/git-remote";
import { getSyncGallery } from "@features/git-sync";
import type { GalleryGroup, GallerySection } from "@shared/lib/stateGallery";

const pick = (groups: GalleryGroup[], ids: string[]): GalleryGroup[] =>
  groups.filter((group) => ids.includes(group.id));

/**
 * Разделы галереи: сверху вниз так, как человек идёт по работе с git. Группы
 * собирают фичи, а здесь они только расставлены по разделам.
 */
export const buildGallerySections = (): GallerySection[] => {
  const remoteStatic = getRemoteStaticGallery();
  const remoteLive = getRemoteLiveGallery();
  return [
    {
      id: "sync",
      title: "Кнопка и панели синхронизации",
      groups: getSyncGallery(),
    },
    {
      id: "connect",
      title: "Подключение репозитория",
      groups: [
        ...pick(remoteStatic, [
          "connect-repo",
          "connect-access",
          "connect-check",
          "connect-dialogs",
        ]),
        ...pick(remoteLive, ["live-connect"]),
      ],
    },
    {
      id: "profile",
      title: "Автор версий",
      groups: getProfileGallery(),
    },
    {
      id: "clone",
      title: "Клонирование проекта",
      groups: [
        ...pick(remoteStatic, ["clone-verdict", "clone-folder"]),
        ...pick(remoteLive, ["live-clone"]),
      ],
    },
    {
      id: "conflicts",
      title: "Разбор конфликтов",
      groups: getConflictsGallery(),
    },
    {
      id: "exchange",
      title: "Обмен файлом и автосборка",
      groups: getExchangeGallery(),
    },
    {
      id: "settings",
      title: "Настройки",
      groups: pick(remoteLive, ["live-settings", "live-access"]),
    },
  ];
};
