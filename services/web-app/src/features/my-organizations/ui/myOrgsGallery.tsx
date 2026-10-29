import type { MyOrg } from "@entities/session";
import type { GalleryEntry, GalleryGroup } from "@shared/lib/stateGallery";
import { MyOrganizationsSection } from "./MyOrganizationsSection";
import { MyOrganizationsView } from "./MyOrganizationsView";

const W = 560;
const noop = () => undefined;

const MEMBER: MyOrg = {
  slug: "msp-2025",
  name: "МСПИН 2025",
  my_role: "member",
  member_count: 6,
  groups: ["Команда Bertie"],
  sole_owner: false,
};
const ADMIN: MyOrg = {
  slug: "ai-lab",
  name: "Лаборатория ИИ",
  my_role: "admin",
  member_count: 3,
  groups: [],
  sole_owner: false,
};
const SOLE: MyOrg = {
  slug: "pilot-2026",
  name: "Пилот 2026",
  my_role: "owner",
  member_count: 1,
  groups: [],
  sole_owner: true,
};

const entry = (
  id: string,
  title: string,
  render: GalleryEntry["render"],
  extra: Partial<GalleryEntry> = {},
): GalleryEntry => ({ id, title, frame: "window", width: W, render, ...extra });

const view = (
  extra: Partial<Parameters<typeof MyOrganizationsView>[0]> = {},
) => (
  <MyOrganizationsView
    status="ready"
    orgs={[MEMBER, ADMIN, SOLE]}
    onLeave={noop}
    {...extra}
  />
);

/** Раздел «Организации» в настройках участника: все состояния. */
export const getMyOrganizationsGallery = (): GalleryGroup[] => [
  {
    id: "my-orgs",
    title: "Настройки: организации",
    entries: [
      entry("my_orgs", "Роли: участник, админ, единственный владелец", () =>
        view(),
      ),
      entry("my_orgs_empty", "Нет организаций", () => view({ orgs: [] })),
      entry("my_orgs_loading", "Загрузка", () =>
        view({ status: "loading", orgs: [] }),
      ),
      entry("my_orgs_error", "Не загрузились", () =>
        view({ status: "error", orgs: [], onRetry: noop }),
      ),
      entry("my_orgs_leaving", "Идёт выход", () =>
        view({ leavingSlug: "msp-2025" }),
      ),
      entry("my_orgs_failed", "Выйти не вышло", () =>
        view({ failure: { code: "network" } }),
      ),
      entry("my_orgs_last_owner", "Сервер отказал: последний владелец", () =>
        view({ failure: { code: "last_owner" } }),
      ),
    ],
  },
  {
    id: "my-orgs-live",
    title: "Настройки: организации (живой раздел)",
    description:
      "На демо-мире. Студент состоит в одной организации и может выйти; админ установки единственный владелец и выйти не может.",
    entries: [
      entry(
        "my_orgs_live_student",
        "Студент",
        () => <MyOrganizationsSection />,
        {
          scenario: "student_ready",
        },
      ),
      entry(
        "my_orgs_live_admin",
        "Админ установки",
        () => <MyOrganizationsSection />,
        {
          scenario: "admin_ready",
        },
      ),
      entry(
        "my_orgs_live_none",
        "Админ без организаций",
        () => <MyOrganizationsSection />,
        {
          scenario: "admin_no_orgs",
        },
      ),
    ],
  },
];
