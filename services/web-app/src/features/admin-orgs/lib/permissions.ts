import type { AdminOrgMember, OrgRoleName } from "@entities/session";

// Кто что может в организации. Сервер проверяет то же самое: здесь только то, что
// решает, какие кнопки показать.

export type Viewer = {
  instanceAdmin: boolean;
  /** Роль смотрящего в этой организации; null у админа установки, который в ней не состоит. */
  role: OrgRoleName | null;
};

export const ROLES: readonly OrgRoleName[] = ["owner", "admin", "member"];

/** Владелец и админ установки распоряжаются всем, админ организации только рядовыми. */
export const isFull = (viewer: Viewer): boolean =>
  viewer.instanceAdmin || viewer.role === "owner";

/** Роли, которые смотрящий вправе выдавать. */
export const assignableRoles = (viewer: Viewer): readonly OrgRoleName[] =>
  isFull(viewer) ? ROLES : ROLES.filter((r) => r !== "owner");

/** Можно ли менять роль или убирать этого участника. */
export const canEditMember = (viewer: Viewer, target: OrgRoleName): boolean =>
  isFull(viewer) || target !== "owner";

/**
 * Единственный владелец: его нельзя ни понизить, ни убрать. Весь состав
 * клиенту не виден, поэтому число владельцев берётся из организации
 * (owner_count). Без него замка нет: последнего владельца всё равно защищает
 * сервер (409).
 */
export const isLastOwner = (
  member: AdminOrgMember,
  ownerCount: number | null = null,
): boolean => member.role === "owner" && ownerCount !== null && ownerCount <= 1;

/** Организации создаёт и удаляет только админ установки. */
export const canCreateOrg = (viewer: Pick<Viewer, "instanceAdmin">): boolean =>
  viewer.instanceAdmin;
