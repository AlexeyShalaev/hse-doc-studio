import type { QueryClient } from "@tanstack/react-query";
import { profileKeys } from "@entities/profile";
import type { GalleryGroup } from "@shared/lib/stateGallery";
import { DialogLauncher } from "@shared/ui/StateGallery";
import { AuthorProfileSection } from "../ui/AuthorProfileSection";
import {
  ProfilePromptDialog,
  type ProfilePromptReason,
} from "../ui/ProfilePromptDialog";

const noop = (): void => undefined;

const DEFAULT_PROFILE = {
  name: null,
  email: null,
  effective_name: "HSE Doc Studio",
  effective_email: "studio@hse-doc-studio.local",
  is_default: true,
  commit_preview: "HSE Doc Studio <studio@hse-doc-studio.local>",
};

const SET_PROFILE = {
  name: "Иван Смирнов",
  email: "ivan@edu.hse.ru",
  effective_name: "Иван Смирнов",
  effective_email: "ivan@edu.hse.ru",
  is_default: false,
  commit_preview: "Иван Смирнов <ivan@edu.hse.ru>",
};

const REASONS: { reason: ProfilePromptReason; title: string }[] = [
  { reason: "connect", title: "при подключении репозитория" },
  { reason: "sync", title: "при синхронизации" },
  { reason: "clone", title: "при клонировании" },
];

/** Автор версий: раздел настроек и окно «Представься» на каждый повод. */
export const getProfileGallery = (): GalleryGroup[] => [
  {
    id: "profile",
    title: "Раздел настроек и окно «Представься»",
    entries: [
      {
        id: "profile_section_default",
        title: "Раздел настроек: автор не указан",
        note: "Предупреждение, что версии подписаны именем Студии, и форма.",
        frame: "window",
        seed: (client) => {
          client.setQueryData(profileKeys.current(), DEFAULT_PROFILE);
        },
        render: () => <AuthorProfileSection />,
      },
      {
        id: "profile_section_set",
        title: "Раздел настроек: автор указан",
        note: "Предпросмотр подписи версии и кнопка вернуть общую подпись.",
        frame: "window",
        seed: (client) => {
          client.setQueryData(profileKeys.current(), SET_PROFILE);
        },
        render: () => <AuthorProfileSection />,
      },
      ...REASONS.map(({ reason, title }) => ({
        id: `profile_dialog_${reason}`,
        title: `Окно «Представься» ${title}`,
        note: "Пояснение под заголовком зависит от того, что прервалось.",
        frame: "plain" as const,
        seed: (client: QueryClient) => {
          client.setQueryData(profileKeys.current(), DEFAULT_PROFILE);
        },
        render: () => (
          <DialogLauncher label="Открыть окно">
            {({ isOpen, close }) => (
              <ProfilePromptDialog
                isOpen={isOpen}
                onClose={close}
                onSaved={noop}
                reason={reason}
              />
            )}
          </DialogLauncher>
        ),
      })),
    ],
  },
];
