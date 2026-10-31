import type { ProjectRole, ProjectSummary } from "@entities/session";
import { DEMO_ADMIN, DEMO_STUDENT } from "./scenarios";

// Проекты серверного демо. У каждого своя роль у каждого человека; у кого роли
// нет, тот проект не видит и получает 404, как на настоящем сервере.

export type DemoProject = {
  summary: Omit<ProjectSummary, "my_role">;
  /** Роли людей, выданные напрямую. Итоговую роль считает effectiveRole. */
  roles: Record<string, ProjectRole>;
  /** Роли групп организаций: каждый участник группы получает эту роль. */
  groupRoles?: Record<string, ProjectRole>;
  /** Право «Может делиться» у прямых редакторов (ACCESS_MANAGE без роли владельца). */
  canShare?: Record<string, boolean>;
};

const OWNER_PAVEL = {
  kind: "user" as const,
  id: "u_01hx7k5pavel",
  name: "Павел Орлов",
  slug: null,
};
const ORG = {
  kind: "org" as const,
  id: "org_01hx5a",
  name: "МСПИН 2025",
  slug: "msp-2025",
};

const base = {
  kind: "project" as const,
  staffing: "solo" as const,
  lang: "ru" as const,
  pinned: false,
  archived: false,
  shared_enabled: true,
};

export const DEMO_FOREIGN_PROJECT_ID = "p_01hxa9foreign";

export const seedProjects = (): DemoProject[] => [
  {
    summary: {
      ...base,
      id: "p_01hxa1c4de",
      name: "Bertie: курсовой проект",
      staffing: "team",
      owner: {
        kind: "user",
        id: DEMO_STUDENT.id,
        name: DEMO_STUDENT.name,
        slug: null,
      },
      updated_at: "2026-10-26T18:20:00Z",
      pinned: true,
    },
    roles: { [DEMO_STUDENT.id]: "owner", [DEMO_ADMIN.id]: "editor" },
    groupRoles: { g_01hx7m4c2d: "editor" },
    canShare: { [DEMO_ADMIN.id]: true },
  },
  {
    summary: {
      ...base,
      id: "p_01hxa2f8gh",
      name: "Industry adoption of CI",
      kind: "research",
      lang: "en",
      owner: ORG,
      updated_at: "2026-10-24T10:05:00Z",
    },
    roles: { [DEMO_STUDENT.id]: "reviewer", [DEMO_ADMIN.id]: "owner" },
    groupRoles: { g_01hx7m5d3e: "reviewer" },
  },
  {
    summary: {
      ...base,
      id: "p_01hxa3k2jm",
      name: "Анализ нагрузки на очередь задач",
      owner: OWNER_PAVEL,
      updated_at: "2026-10-22T09:40:00Z",
    },
    roles: { [DEMO_STUDENT.id]: "reader" },
  },
  {
    summary: {
      ...base,
      id: "p_01hxa4n7pq",
      name: "Практика 2025: отчёт",
      kind: "research",
      owner: {
        kind: "user",
        id: DEMO_STUDENT.id,
        name: DEMO_STUDENT.name,
        slug: null,
      },
      updated_at: "2026-06-30T12:00:00Z",
      archived: true,
    },
    roles: { [DEMO_STUDENT.id]: "owner" },
  },
  {
    summary: {
      ...base,
      id: DEMO_FOREIGN_PROJECT_ID,
      name: "Чужой проект",
      owner: {
        kind: "user",
        id: "u_01hx7k8maria",
        name: "Мария Келлер",
        slug: null,
      },
      updated_at: "2026-10-20T08:00:00Z",
    },
    roles: {},
  },
];
