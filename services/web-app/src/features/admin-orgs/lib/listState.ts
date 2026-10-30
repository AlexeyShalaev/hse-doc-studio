import type { ListStateOptions } from "@shared/lib";
import type { OrgRoleName } from "@entities/session";

// Состояние серверных списков раздела в адресе. Описание общее у загрузки и
// у экрана: оба читают одни и те же ключи, а чужие значения отбрасываются.
// У участников и групп свои приставки: обе вкладки живут на одной странице.

const ROLE_VALUES: readonly OrgRoleName[] = ["owner", "admin", "member"];

export type OrgsSort = "name" | "slug" | "member_count" | "project_count";
export const ORGS_LIST: ListStateOptions<"mine", OrgsSort> = {
  filters: { mine: { values: ["true", "false"] } },
  sort: {
    fields: ["name", "slug", "member_count", "project_count"],
    default: "name",
  },
};
export const ORGS_SORTABLE: readonly OrgsSort[] = [
  "name",
  "member_count",
  "project_count",
];

export type MembersSort = "name" | "email" | "role" | "joined_at";
export const MEMBERS_LIST: ListStateOptions<"role", MembersSort> = {
  prefix: "m.",
  filters: { role: { multi: true, values: ROLE_VALUES } },
  sort: {
    fields: ["name", "email", "role", "joined_at"],
    default: "joined_at",
  },
};
export const MEMBERS_SORTABLE: readonly MembersSort[] = [
  "name",
  "role",
  "joined_at",
];

export type GroupsSort = "name" | "member_count";
export const GROUPS_LIST: ListStateOptions<never, GroupsSort> = {
  prefix: "g.",
  sort: { fields: ["name", "member_count"], default: "name" },
  pageSize: 25,
};
