import { useEffect, useState, type ReactNode } from "react";
import type { AdminGroup, AdminOrg, AdminOrgMember } from "@entities/session";
import type { GalleryEntry, GalleryGroup } from "@shared/lib/stateGallery";
import { ensureAdminOrgsLocales } from "../lib/locales";
import type { Viewer } from "../lib/permissions";
import { GroupsView, type GroupsViewProps } from "./GroupsView";
import { MembersView, type MembersViewProps } from "./MembersView";
import { OrgDetail } from "./OrgDetail";
import {
  OrgDetailView,
  type OrgDetailViewProps,
  type OrgTab,
} from "./OrgDetailView";
import { OrgsList } from "./OrgsList";
import { OrgsListView, type OrgsListViewProps } from "./OrgsListView";
import { CreateOrgForm } from "./CreateOrgModal";

const W = 760;
const noop = () => undefined;

/** Словарь организаций грузится вместе с чанком админки; галерея ждёт его сама. */
const Ready = ({ children }: { children: ReactNode }) => {
  const [ready, setReady] = useState(false);
  useEffect(() => {
    let live = true;
    void ensureAdminOrgsLocales().then(() => {
      if (live) setReady(true);
    });
    return () => {
      live = false;
    };
  }, []);
  return ready ? <>{children}</> : null;
};

const ORGS: AdminOrg[] = [
  {
    slug: "msp-2025",
    name: "МСПИН 2025",
    member_count: 6,
    project_count: 31,
    my_role: "owner",
  },
  {
    slug: "ai-lab",
    name: "Лаборатория ИИ",
    member_count: 3,
    project_count: 4,
    my_role: "admin",
  },
  {
    slug: "pilot-2026",
    name: "Пилот 2026",
    member_count: 1,
    project_count: 0,
    my_role: null,
  },
];

const m = (
  id: string,
  name: string,
  role: AdminOrgMember["role"],
  joined: string,
): AdminOrgMember => ({
  user_id: id,
  name,
  email: `${id}@example.org`,
  role,
  joined_at: joined,
});

const MEMBERS: AdminOrgMember[] = [
  m("ivan", "Иван Сидоров", "owner", "2026-09-12T10:05:00Z"),
  m("elena", "Елена Миронова", "admin", "2026-09-13T09:00:00Z"),
  m("anna", "Анна Петрова", "member", "2026-09-14T08:30:00Z"),
  m("petr", "Пётр Орлов", "member", "2026-09-14T08:41:00Z"),
  m("olga", "Ольга Белова", "member", "2026-09-15T12:10:00Z"),
  m("dmitry", "Дмитрий Кузнецов", "member", "2026-09-18T16:20:00Z"),
].map((x) => ({ ...x, is_last_owner: x.user_id === "ivan" }));

const group = (id: string, name: string, ids: string[]): AdminGroup => {
  const people = MEMBERS.filter((x) => ids.includes(x.user_id));
  return {
    id,
    name,
    member_count: people.length,
    preview: people
      .slice(0, 5)
      .map((x) => ({ user_id: x.user_id, name: x.name })),
  };
};

const GROUPS: AdminGroup[] = [
  group("g1", "Команда Bertie", ["anna", "petr", "olga"]),
  group("g2", "Наставники", ["elena"]),
  group("g3", "Все студенты", [
    "anna",
    "petr",
    "olga",
    "dmitry",
    "elena",
    "ivan",
  ]),
  group("g4", "Резерв", []),
];

const FULL: Viewer = { instanceAdmin: true, role: null };
const OWNER: Viewer = { instanceAdmin: false, role: "owner" };
const ADMIN: Viewer = { instanceAdmin: false, role: "admin" };

const entry = (
  id: string,
  title: string,
  render: () => ReactNode,
  extra: Partial<GalleryEntry> = {},
): GalleryEntry => ({
  id,
  title,
  frame: "window",
  width: W,
  render: () => <Ready>{render()}</Ready>,
  ...extra,
});

const list = (extra: Partial<OrgsListViewProps> = {}) => (
  <OrgsListView
    status="ready"
    orgs={ORGS}
    canCreate
    onOpen={noop}
    onCreate={noop}
    {...extra}
  />
);

const members = (extra: Partial<MembersViewProps> = {}) => (
  <MembersView
    status="ready"
    members={MEMBERS}
    viewer={FULL}
    selfId="ivan"
    total={MEMBERS.length}
    roleCounts={{ owner: 1, admin: 1, member: 4 }}
    onAdd={() => undefined}
    onSetRole={noop}
    onRemove={() => undefined}
    {...extra}
  />
);

const groups = (extra: Partial<GroupsViewProps> = {}) => (
  <GroupsView
    status="ready"
    groups={GROUPS}
    total={GROUPS.length}
    onCreate={() => undefined}
    onRename={() => undefined}
    onDelete={() => undefined}
    {...extra}
  />
);

const detail = (
  tab: OrgTab,
  children: ReactNode,
  extra: Partial<OrgDetailViewProps> = {},
) => (
  <OrgDetailView
    status="ready"
    org={ORGS[0] ?? null}
    tab={tab}
    onTab={noop}
    onBack={noop}
    canDelete
    onDelete={noop}
    {...extra}
  >
    {children}
  </OrgDetailView>
);

/** Организации в админке: список, страница организации, участники и группы; живые разделы на демо-мире. */
export const getAdminOrgsGallery = (): GalleryGroup[] => [
  {
    id: "admin-orgs-list",
    title: "Админка: список организаций",
    entries: [
      entry("admin_orgs_list", "Админ установки", () => list()),
      entry(
        "admin_orgs_list_orgadmin",
        "Админ организации",
        () => list({ orgs: ORGS.slice(0, 2), canCreate: false }),
        { note: "Только свои организации, кнопки создания нет." },
      ),
      entry("admin_orgs_empty", "Организаций нет", () => list({ orgs: [] })),
      entry("admin_orgs_loading", "Загрузка", () =>
        list({ status: "loading", orgs: [] }),
      ),
      entry("admin_orgs_error", "Не загрузился", () =>
        list({ status: "error", orgs: [], onRetry: noop }),
      ),
    ],
  },
  {
    id: "admin-orgs-create",
    title: "Админка: создание организации",
    entries: [
      entry("admin_org_create", "Пустая форма", () => (
        <CreateOrgForm onCancel={noop} onSubmit={noop} />
      )),
      entry("admin_org_create_pending", "Создаётся", () => (
        <CreateOrgForm pending onCancel={noop} onSubmit={noop} />
      )),
      entry("admin_org_create_taken", "Отказ: адрес занят", () => (
        <CreateOrgForm
          failure={{ code: "slug_taken" }}
          onCancel={noop}
          onSubmit={noop}
        />
      )),
      entry("admin_org_create_reserved", "Отказ: адрес зарезервирован", () => (
        <CreateOrgForm
          failure={{ code: "slug_reserved" }}
          onCancel={noop}
          onSubmit={noop}
        />
      )),
    ],
  },
  {
    id: "admin-orgs-detail",
    title: "Админка: страница организации",
    entries: [
      entry("admin_org_detail", "Участники, админ установки", () =>
        detail("members", members()),
      ),
      entry("admin_org_detail_groups", "Группы", () =>
        detail("groups", groups(), { groupCount: GROUPS.length }),
      ),
      entry("admin_org_detail_settings", "Настройки и опасная зона", () =>
        detail("settings", null),
      ),
      entry("admin_org_detail_loading", "Загрузка", () =>
        detail("members", null, { status: "loading", org: null }),
      ),
      entry("admin_org_detail_error", "Не загрузилась", () =>
        detail("members", null, { status: "error", org: null, onRetry: noop }),
      ),
      entry(
        "admin_org_detail_missing",
        "Нет такой или чужая",
        () => detail("members", null, { status: "missing", org: null }),
        { note: "Чужая и несуществующая выглядят одинаково." },
      ),
      entry("admin_org_detail_orgadmin", "Админ организации", () =>
        detail("members", members({ viewer: ADMIN, selfId: "elena" }), {
          canDelete: false,
          org: ORGS[1] ?? null,
        }),
      ),
      entry(
        "admin_org_settings_orgadmin",
        "Настройки: админ организации",
        () =>
          detail("settings", null, { canDelete: false, org: ORGS[1] ?? null }),
        { note: "Удалять организацию может только админ установки." },
      ),
    ],
  },
  {
    id: "admin-orgs-members",
    title: "Админка: участники",
    entries: [
      entry("admin_members_full", "Админ установки видит всё", () => members()),
      entry(
        "admin_members_owner",
        "Владелец организации",
        () => members({ viewer: OWNER }),
        { note: "Единственного владельца нельзя понизить и убрать." },
      ),
      entry(
        "admin_members_admin",
        "Админ организации",
        () => members({ viewer: ADMIN, selfId: "elena" }),
        { note: "Владельцев не трогает, владельцем не назначает." },
      ),
      entry("admin_members_empty", "Участников нет", () =>
        members({ members: [] }),
      ),
      entry("admin_members_loading", "Загрузка", () =>
        members({ status: "loading", members: [] }),
      ),
      entry("admin_members_error", "Не загрузились", () =>
        members({ status: "error", members: [], onRetry: noop }),
      ),
      entry("admin_members_adding", "Добавляется", () =>
        members({ adding: true }),
      ),
      entry("admin_members_add_notfound", "Отказ: нет такого человека", () =>
        members({ addFailure: { code: "not_found" } }),
      ),
      entry("admin_members_add_already", "Отказ: уже в организации", () =>
        members({ addFailure: { code: "already_member" } }),
      ),
      entry("admin_members_lastowner", "Отказ: последний владелец", () =>
        members({ failure: { code: "last_owner" } }),
      ),
      entry("admin_members_busy", "Меняется роль", () =>
        members({ busyUserId: "anna" }),
      ),
    ],
  },
  {
    id: "admin-orgs-groups",
    title: "Админка: группы",
    entries: [
      entry("admin_groups", "Четыре группы", () => groups()),
      entry("admin_groups_empty", "Групп нет", () => groups({ groups: [] })),
      entry("admin_groups_loading", "Загрузка", () =>
        groups({ status: "loading", groups: [] }),
      ),
      entry("admin_groups_error", "Не загрузились", () =>
        groups({ status: "error", groups: [], onRetry: noop }),
      ),
      entry("admin_groups_failed", "Отказ удаления", () =>
        groups({ failure: { code: "network" } }),
      ),
      entry(
        "admin_groups_nomembers",
        "В организации нет людей",
        () => groups({ groups: [], memberSource: null }),
        { note: "В форме создания группы выбирать некого." },
      ),
    ],
  },
  {
    id: "admin-orgs-live",
    title: "Админка: организации, живой раздел",
    description:
      "На демо-мире. Адрес участника вне списка людей даёт отказ. У МСПИН 2025 есть проекты, поэтому удалить её нельзя; Пилот 2026 удаляется. Адреса admin и api зарезервированы.",
    entries: [
      entry(
        "admin_orgs_live",
        "Админ установки: список",
        () => <OrgsListLive />,
        {
          scenario: "admin_ready",
        },
      ),
      entry(
        "admin_orgs_live_detail",
        "Админ установки: МСПИН 2025",
        () => <OrgDetail slug="msp-2025" onBack={noop} onDeleted={noop} />,
        { scenario: "admin_ready" },
      ),
      entry(
        "admin_orgs_live_pilot",
        "Админ установки: Пилот 2026 (удаляется)",
        () => <OrgDetail slug="pilot-2026" onBack={noop} onDeleted={noop} />,
        { scenario: "admin_ready" },
      ),
      entry(
        "admin_orgs_live_orgadmin",
        "Админ организации: список",
        () => <OrgsListLive />,
        {
          scenario: "org_admin",
        },
      ),
      entry(
        "admin_orgs_live_empty",
        "Нет организаций",
        () => <OrgsListLive />,
        {
          scenario: "admin_no_orgs",
        },
      ),
    ],
  },
];

const OrgsListLive = () => <OrgsList onOpen={noop} />;
