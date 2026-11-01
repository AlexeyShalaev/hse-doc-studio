import type { GuestInfo } from "@entities/session";
import type { GalleryEntry, GalleryGroup } from "@shared/lib/stateGallery";
import {
  GuestBadgeView,
  GuestLeaveDialog,
  GuestRenameDialog,
} from "./GuestBadge";
import { GuestProjectsView } from "./GuestHome";
import { LinkAccessBanner } from "./LinkAccessBanner";
import { LinkRevokedScreen } from "./LinkRevokedScreen";

const noop = () => undefined;

const DEMO_GUEST: GuestInfo = {
  name: "Борис",
  links: [
    {
      project_id: "p_01hxa1c4de",
      project_name: "ВКР: Анализ требований",
      link_label: "Для группы",
      role: "editor",
      show_sources: true,
    },
    {
      project_id: "p_01hxa3k2jm",
      project_name: "Анализ нагрузки на очередь задач",
      link_label: "Для научрука",
      role: "reader",
      show_sources: false,
    },
  ],
};

const entry = (
  id: string,
  title: string,
  render: GalleryEntry["render"],
  extra: Partial<GalleryEntry> = {},
): GalleryEntry => ({
  id,
  title,
  frame: "window",
  width: 640,
  render,
  ...extra,
});

/** Гость в приложении (10.4): бейдж и меню, баннер, отзыв ссылки, проекты гостя. */
export const getGuestSessionGallery = (): GalleryGroup[] => [
  {
    id: "guest-session",
    title: "Гость по ссылке",
    entries: [
      entry(
        "guest_badge_menu",
        "Шапка: «Гость: Борис» и меню",
        () => (
          <div
            style={{
              display: "flex",
              justifyContent: "flex-end",
              padding: 8,
              minHeight: 220,
            }}
          >
            <GuestBadgeView
              guest={DEMO_GUEST}
              defaultOpen
              onRename={noop}
              onSignIn={noop}
              onLeave={noop}
            />
          </div>
        ),
        { frame: "plain" },
      ),
      entry("guest_projects", "Главная гостя: проекты по ссылкам", () => (
        <GuestProjectsView guest={DEMO_GUEST} />
      )),
      entry("guest_projects_empty", "Главная гостя: ссылок не осталось", () => (
        <GuestProjectsView guest={{ name: "Борис", links: [] }} />
      )),
      entry("guest_banner_editor", "Баннер: гость-редактор", () => (
        <LinkAccessBanner label="Для группы" role="editor" showSources guest />
      )),
      entry(
        "guest_banner_reader_user",
        "Баннер: вошедший читатель по ссылке",
        () => (
          <LinkAccessBanner
            label="Для научрука"
            role="reader"
            showSources={false}
            guest={false}
          />
        ),
      ),
      entry("guest_revoked", "Ссылку отозвали посреди работы", () => (
        <LinkRevokedScreen />
      )),
      entry(
        "guest_rename",
        "Сменить имя",
        () => (
          <GuestRenameDialog
            isOpen
            initial="Борис"
            onSave={noop}
            onClose={noop}
          />
        ),
        { frame: "plain" },
      ),
      entry(
        "guest_leave",
        "Выйти из гостевого режима",
        () => <GuestLeaveDialog isOpen onConfirm={noop} onClose={noop} />,
        { frame: "plain" },
      ),
    ],
  },
];
