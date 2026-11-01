import type { ShareLinkPreview } from "@entities/share-link";
import type { GalleryEntry, GalleryGroup } from "@shared/lib/stateGallery";
import { ShareLinkView, type ShareLinkViewProps } from "./ShareLinkView";

const noop = () => undefined;

const OK: ShareLinkPreview = {
  state: "ok",
  project_name: "ВКР: Анализ требований",
  owner_name: "Анна Петрова",
  role: "reader",
  show_sources: false,
  guest_name_required: false,
  signed_in: false,
};
const HIDDEN: ShareLinkPreview = {
  state: "password_required",
  project_name: null,
  owner_name: null,
  role: null,
  show_sources: false,
  guest_name_required: false,
  signed_in: false,
};

const card = (extra: Partial<ShareLinkViewProps>) => (
  <div style={{ maxWidth: 400, margin: "0 auto", padding: 24 }}>
    <ShareLinkView
      status="ready"
      preview={OK}
      onOpen={noop}
      loginHref="/login"
      {...extra}
    />
  </div>
);

const entry = (
  id: string,
  title: string,
  render: GalleryEntry["render"],
): GalleryEntry => ({
  id,
  title,
  frame: "window",
  width: 480,
  render,
});

/** Страница ссылки `/s/:token` (10.3) во всех состояниях превью. */
export const getShareLinkPageGallery = (): GalleryGroup[] => [
  {
    id: "share-link-page",
    title: "Страница ссылки",
    entries: [
      entry("page_reader", "Читатель: только PDF", () => card({})),
      entry("page_editor", "Редактор: нужно имя", () =>
        card({
          preview: {
            ...OK,
            role: "editor",
            show_sources: true,
            guest_name_required: true,
          },
        }),
      ),
      entry("page_signed_in", "Вошедший: «Вы войдёте как…»", () =>
        card({
          preview: {
            ...OK,
            role: "reviewer",
            show_sources: true,
            signed_in: true,
          },
          signedInName: "Вера Смирнова",
        }),
      ),
      entry("page_password", "Нужен пароль", () => card({ preview: HIDDEN })),
      entry("page_password_wrong", "Неверный пароль", () =>
        card({ preview: HIDDEN, error: "Неверный пароль" }),
      ),
      entry("page_login", "Нужен вход", () =>
        card({ preview: { ...OK, state: "login_required" } }),
      ),
      entry("page_org_only", "Только для участников организации", () =>
        card({
          preview: { ...OK, state: "org_only", owner_name: "МСПИН 2025" },
        }),
      ),
      entry("page_inactive", "Ссылка не действует", () =>
        card({ preview: { ...HIDDEN, state: "inactive" } }),
      ),
      entry("page_loading", "Проверка ссылки", () =>
        card({ status: "loading", preview: null }),
      ),
    ],
  },
];
