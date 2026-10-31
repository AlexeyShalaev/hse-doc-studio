import type { ShareLink, ShareLinkList } from "@entities/share-link";
import type { GalleryEntry, GalleryGroup } from "@shared/lib/stateGallery";
import { LinkVisitsModal, ShareLinkForm } from "./ShareLinkDialogs";
import { ShareLinksView, type ShareLinksViewProps } from "./ShareLinksView";
import "./shareLinks.css";

const W = 640;
const NOW = Date.parse("2026-11-01T16:00:00Z");
const noop = () => undefined;

const DEMO_READER_LINK: ShareLink = {
  id: "lnk_3f2a1b0c9d8e4f7a6b5c4d3e2f1a0b9c",
  label: "Для научрука",
  role: "reader",
  show_sources: false,
  require_login: false,
  has_password: false,
  url: "https://studio.example.org/s/hsl_bG9uZ1JhbmRvbVRva2VuRXhhbXBsZVZhbHVlMDE",
  token_prefix: "bG9uZ1Jh",
  created_by: { id: "u_01hx7k2m9c", name: "Анна Петрова" },
  created_at: "2026-11-01T09:00:00Z",
  updated_at: "2026-11-01T09:00:00Z",
  expires_at: "2026-12-31T00:00:00Z",
  state: "active",
  blocked_reason: null,
  editable: true,
  visits: { visitors: 1, opens: 3, last_at: "2026-11-01T14:02:00Z" },
};

const DEMO_EDITOR_LINK: ShareLink = {
  ...DEMO_READER_LINK,
  id: "lnk_9e8d7c6b5a4f40312233445566778899",
  label: "Для группы",
  role: "editor",
  show_sources: true,
  has_password: true,
  url: "https://studio.example.org/s/hsl_ZWRpdG9yTGlua1Rva2VuRXhhbXBsZVZhbHVlMDI",
  token_prefix: "ZWRpdG9y",
  expires_at: null,
  visits: { visitors: 0, opens: 0, last_at: null },
};

const list = (
  items: ShareLink[],
  extra: Partial<ShareLinkList> = {},
): ShareLinkList => ({
  items,
  can_create: true,
  max_role: "editor",
  forced_login: false,
  revoked_count: 0,
  ...extra,
});

const view = (extra: Partial<ShareLinksViewProps> = {}) => (
  <ShareLinksView
    status="ready"
    list={list([DEMO_READER_LINK, DEMO_EDITOR_LINK])}
    showRevoked={false}
    onToggleRevoked={noop}
    onCreate={noop}
    onEdit={noop}
    onRotate={noop}
    onRevoke={noop}
    onVisits={noop}
    now={NOW}
    {...extra}
  />
);

const entry = (
  id: string,
  title: string,
  render: GalleryEntry["render"],
  extra: Partial<GalleryEntry> = {},
): GalleryEntry => ({ id, title, frame: "window", width: W, render, ...extra });

/** «Доступ по ссылке» (10.2): список во всех состояниях, форма, переходы. */
export const getShareLinksGallery = (): GalleryGroup[] => [
  {
    id: "share-links",
    title: "Проект: доступ по ссылке",
    entries: [
      entry("links_two", "Две ссылки: Читатель и Редактор с паролем", () =>
        view(),
      ),
      entry("links_empty", "Ссылок нет", () => view({ list: list([]) })),
      entry(
        "links_states",
        "Истекла, не действует по политике, отозванные",
        () =>
          view({
            list: list(
              [
                {
                  ...DEMO_READER_LINK,
                  state: "expired",
                  url: null,
                  expires_at: "2026-10-01T00:00:00Z",
                },
                {
                  ...DEMO_EDITOR_LINK,
                  state: "blocked",
                  blocked_reason: "org_links_off",
                },
                {
                  ...DEMO_READER_LINK,
                  id: "lnk_revoked",
                  label: "Старая ссылка",
                  state: "revoked",
                  url: null,
                  editable: false,
                },
              ],
              { revoked_count: 1 },
            ),
            showRevoked: true,
          }),
      ),
      entry("links_nda", "Проект под NDA: вход обязателен", () =>
        view({
          list: list(
            [
              { ...DEMO_READER_LINK, require_login: true },
              { ...DEMO_EDITOR_LINK, state: "blocked", blocked_reason: "nda" },
            ],
            { forced_login: true },
          ),
        }),
      ),
      entry("links_blocked_create", "Ссылки запрещены: создать нельзя", () =>
        view({ list: list([], { can_create: false }) }),
      ),
      entry("links_loading", "Загрузка", () =>
        view({ status: "loading", list: null }),
      ),
      entry("links_error", "Не загрузились", () =>
        view({ status: "error", list: null, onRetry: noop }),
      ),
      entry(
        "links_form_create",
        "Форма: новая ссылка",
        () => (
          <ShareLinkForm
            isOpen
            link={null}
            maxRole="reviewer"
            forcedLogin={false}
            onSubmit={noop}
            onClose={noop}
          />
        ),
        { frame: "plain" },
      ),
      entry(
        "links_form_edit",
        "Форма: правка ссылки с паролем, вход обязателен",
        () => (
          <ShareLinkForm
            isOpen
            link={DEMO_EDITOR_LINK}
            maxRole="editor"
            forcedLogin
            onSubmit={noop}
            onClose={noop}
          />
        ),
        { frame: "plain" },
      ),
      entry(
        "links_visits",
        "Переходы по ссылке",
        () => (
          <LinkVisitsModal
            link={DEMO_READER_LINK}
            status="ready"
            items={[
              {
                visitor_kind: "guest",
                name: "Пётр Иванович",
                first_at: "2026-11-01T13:50:00Z",
                last_at: "2026-11-01T14:02:00Z",
                opens: 3,
              },
              {
                visitor_kind: "user",
                name: "Вера Смирнова",
                first_at: "2026-11-01T12:00:00Z",
                last_at: "2026-11-01T12:00:00Z",
                opens: 1,
              },
            ]}
            onClose={noop}
          />
        ),
        { frame: "plain" },
      ),
    ],
  },
];
