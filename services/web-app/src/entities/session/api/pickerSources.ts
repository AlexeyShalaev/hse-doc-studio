import { z } from "zod";
import {
  PickerPageSchema,
  adminClient,
  apiClient,
  listPageOf,
  parseResp,
} from "@shared/api";
import type { PickerItem, PickerPage } from "@shared/lib";
import type { PickerSource } from "@shared/ui";

// Источники пикеров (единый контракт, раздел «Пикеры»): куда уходит поиск и
// как по id найти имя для фильтра, открытого по ссылке. Пикер отдаёт только
// то, что вызывающему можно видеть; чужое сервер не находит (404).

const quiet = { silentError: true } as const;
const enc = encodeURIComponent;

// Для подписи по id нужны только имя и вторая строка: остальные поля строки
// меняются вместе с контрактом и здесь не проверяются.
const UserNameSchema = z.object({
  id: z.string(),
  name: z.string(),
  email: z.string(),
});
const OrgNameSchema = z.object({ slug: z.string(), name: z.string() });
const MemberRowSchema = z.object({
  user_id: z.string(),
  name: z.string(),
  email: z.string(),
});
const CandidateSchema = z.object({
  subject_kind: z.enum(["user", "group"]),
  subject_id: z.string(),
  name: z.string(),
  detail: z.string().nullable(),
});
// Кандидаты в проект: до перехода сервера на {items, has_more} шёл массив.
const CandidatesSchema = z.union([
  z.object({ items: z.array(CandidateSchema), has_more: z.boolean() }),
  z.array(CandidateSchema).transform((items) => ({ items, has_more: false })),
]);

const adminPicker =
  (path: string, extra: Record<string, string> = {}) =>
  (q: string, { limit, signal }: { limit: number; signal: AbortSignal }) =>
    adminClient
      .get(path, {
        ...quiet,
        signal,
        params: { ...(q ? { q } : {}), limit, ...extra },
      })
      .then(parseResp(PickerPageSchema));

const resolveUser = (id: string, signal: AbortSignal) =>
  adminClient
    .get(`/users/${enc(id)}`, { ...quiet, signal })
    .then(parseResp(UserNameSchema))
    .then((u): PickerItem => ({
      kind: "user",
      id: u.id,
      name: u.name,
      detail: u.email,
    }));

const resolveOrg = (slug: string, signal: AbortSignal) =>
  adminClient
    .get(`/orgs/${enc(slug)}`, { ...quiet, signal })
    .then(parseResp(OrgNameSchema))
    .then((o): PickerItem => ({
      kind: "org",
      id: o.slug,
      name: o.name,
      detail: o.slug,
    }));

export type UserPickerFilters = {
  /** Только активные аккаунты: для добавления в организацию и передачи. */
  status?: "active";
  /** Исключить участников организации (slug). */
  notInOrg?: string;
  /** Исключить участников группы (id). */
  notInGroup?: string;
};

/** Пикеры админки установки: видят всех. */
export const adminPickers = {
  users: (filters: UserPickerFilters = {}): PickerSource => {
    const extra: Record<string, string> = {};
    if (filters.status) extra.status = filters.status;
    if (filters.notInOrg) extra.not_in_org = filters.notInOrg;
    if (filters.notInGroup) extra.not_in_group = filters.notInGroup;
    return {
      key: ["admin", "pickers", "users", extra],
      search: adminPicker("/pickers/users", extra),
      resolve: resolveUser,
    };
  },
  orgs: (): PickerSource => ({
    key: ["admin", "pickers", "orgs"],
    search: adminPicker("/pickers/orgs"),
    resolve: resolveOrg,
  }),
  projects: (): PickerSource => ({
    key: ["admin", "pickers", "projects"],
    search: adminPicker("/pickers/projects"),
  }),
  runners: (): PickerSource => ({
    key: ["admin", "pickers", "runners"],
    search: adminPicker("/pickers/runners"),
  }),
  /** Участники организации: из них собирают группы. */
  orgMembers: (slug: string): PickerSource => ({
    key: ["admin", "pickers", "org-members", slug],
    search: (q, { limit, signal }) =>
      adminClient
        .get(`/orgs/${enc(slug)}/members`, {
          ...quiet,
          signal,
          params: { ...(q ? { q } : {}), limit, offset: 0, sort: "name" },
        })
        .then(parseResp(listPageOf(MemberRowSchema).loose()))
        .then((page): PickerPage => ({
          items: page.items.map((m) => ({
            kind: "user",
            id: m.user_id,
            name: m.name,
            detail: m.email,
          })),
          has_more: page.total > page.items.length,
        })),
    resolve: resolveUser,
  }),
};

/** Кандидаты в участники проекта: люди и группы общих организаций. */
export const projectCandidatePicker = (
  projectId: string,
  kind?: "user" | "group",
): PickerSource => ({
  key: ["project", projectId, "candidates", kind ?? "all"],
  search: (q, { limit, signal }) =>
    apiClient
      .get(`/projects/${enc(projectId)}/members/candidates`, {
        ...quiet,
        signal,
        params: { ...(q ? { q } : {}), limit, ...(kind ? { kind } : {}) },
      })
      .then(parseResp(CandidatesSchema))
      .then((page): PickerPage => ({
        items: page.items.map((c) => ({
          kind: c.subject_kind,
          id: c.subject_id,
          name: c.name,
          detail: c.detail,
        })),
        has_more: page.has_more,
      })),
});

/** Кому передать проект: люди общих организаций и свои организации (owner, admin). */
export const projectTransferPicker = (
  projectId: string,
  kind: "user" | "org",
): PickerSource => ({
  key: ["project", projectId, "transfer-candidates", kind],
  search: (q, { limit, signal }) =>
    apiClient
      .get(`/projects/${enc(projectId)}/transfer-candidates`, {
        ...quiet,
        signal,
        params: { ...(q ? { q } : {}), limit, kind },
      })
      .then(parseResp(PickerPageSchema)),
});
