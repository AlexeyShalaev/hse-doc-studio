import type { AdminOrgMember, OrgRoleName } from "@entities/session";

// Организации в демо-мире админки: люди установки, организации, участники и группы.
// Участники те же, что в разделе «Пользователи» (adminPeople): по именам и почтам.
// Формы совпадают с contracts/server/fixtures (AdminOrg, AdminOrgMember, AdminGroup).

export type DemoDirectoryUser = { id: string; name: string; email: string };

/** Группа в демо-мире хранит весь состав; наружу уходит число участников и первые по имени (AdminGroup). */
export type DemoGroup = { id: string; name: string; member_ids: string[] };

export type DemoOrg = {
  slug: string;
  name: string;
  /** Проекты организации: пока они есть, удалить её нельзя. */
  project_count: number;
  members: AdminOrgMember[];
  groups: DemoGroup[];
};

export type DemoAdminOrgs = {
  /** Все люди установки: по этим адресам админ организации добавляет участников. */
  directory: DemoDirectoryUser[];
  orgs: DemoOrg[];
};

export const DIRECTORY: readonly DemoDirectoryUser[] = [
  {
    id: "u_01hx7k1a0b",
    name: "Иван Сидоров",
    email: "ivan.sidorov@example.org",
  },
  {
    id: "u_01hx7k2m9c",
    name: "Анна Петрова",
    email: "anna.petrova@example.org",
  },
  {
    id: "u_01hx7k3e5f",
    name: "Елена Миронова",
    email: "elena.mironova@example.org",
  },
  { id: "u_01hx7k4p6g", name: "Пётр Орлов", email: "petr.orlov@example.org" },
  {
    id: "u_01hx7k5q7h",
    name: "Ольга Белова",
    email: "olga.belova@example.org",
  },
  {
    id: "u_01hx7k6r8j",
    name: "Дмитрий Кузнецов",
    email: "dmitry.kuznetsov@example.org",
  },
  {
    id: "u_01hx7k2c1d",
    name: "Мария Келлер",
    email: "maria.keller@example.org",
  },
];

const member = (
  user: DemoDirectoryUser | undefined,
  role: OrgRoleName,
  joined: string,
): AdminOrgMember => {
  if (!user) throw new Error("demo orgs: unknown user");
  return {
    user_id: user.id,
    name: user.name,
    email: user.email,
    role,
    joined_at: joined,
  };
};

const byId = (id: string) => DIRECTORY.find((u) => u.id === id);

const seedOrgs = (): DemoOrg[] => [
  {
    slug: "msp-2025",
    name: "МСПИН 2025",
    project_count: 31,
    members: [
      member(byId("u_01hx7k1a0b"), "owner", "2026-09-12T10:05:00Z"),
      member(byId("u_01hx7k3e5f"), "admin", "2026-09-13T09:00:00Z"),
      member(byId("u_01hx7k2m9c"), "member", "2026-09-14T08:30:00Z"),
      member(byId("u_01hx7k4p6g"), "member", "2026-09-14T08:41:00Z"),
      member(byId("u_01hx7k5q7h"), "member", "2026-09-15T12:10:00Z"),
      member(byId("u_01hx7k6r8j"), "member", "2026-09-18T16:20:00Z"),
    ],
    groups: [
      {
        id: "g_01hx7m4c2d",
        name: "Команда Bertie",
        member_ids: ["u_01hx7k2m9c", "u_01hx7k4p6g", "u_01hx7k5q7h"],
      },
      {
        id: "g_01hx7m5d3e",
        name: "Наставники",
        member_ids: ["u_01hx7k3e5f"],
      },
    ],
  },
  {
    slug: "ai-lab",
    name: "Лаборатория ИИ",
    project_count: 4,
    members: [
      member(byId("u_01hx7k3e5f"), "owner", "2026-10-01T09:00:00Z"),
      member(byId("u_01hx7k1a0b"), "admin", "2026-10-01T09:02:00Z"),
      member(byId("u_01hx7k6r8j"), "member", "2026-10-02T11:00:00Z"),
    ],
    groups: [],
  },
  {
    slug: "pilot-2026",
    name: "Пилот 2026",
    project_count: 0,
    members: [member(byId("u_01hx7k1a0b"), "owner", "2026-10-20T14:00:00Z")],
    groups: [],
  },
];

export const createDemoAdminOrgs = (
  seed: "default" | "empty" = "default",
): DemoAdminOrgs => ({
  directory: DIRECTORY.map((u) => ({ ...u })),
  orgs: seed === "empty" ? [] : seedOrgs(),
});
