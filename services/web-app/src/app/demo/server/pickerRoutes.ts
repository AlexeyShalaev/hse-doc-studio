import type { DemoRoute } from "@shared/api/demo";
import type { AccountStatus } from "@entities/session";
import {
  enumParam,
  invalidQuery,
  pickerList,
  queryOne,
  type DemoPickerItem,
} from "./demoList";
import {
  adminOpsOf,
  adminOrgsOf,
  adminPeopleOf,
  type ServerDemoWorld,
} from "./world";

// Пикеры админки установки (единый контракт, раздел «Пикеры»): до 20 первых по
// имени и has_more. Права проверяет обёртка админских маршрутов: не админу 404.
// Фильтры людей: status=active, not_in_org (адрес организации), not_in_group.

const STATUSES: readonly AccountStatus[] = [
  "active",
  "pending_verification",
  "pending_approval",
  "disabled",
];

export const createPickerRoutes = (
  getWorld: () => ServerDemoWorld,
): DemoRoute[] => {
  /** Проекты, о которых знает мир: большой список или проекты из очереди. */
  const projects = (): DemoPickerItem[] => {
    const world = getWorld();
    if (world.scale) {
      return world.scale.projects.map((p) => ({
        kind: "project",
        id: p.id,
        name: p.name,
        detail: p.org?.name ?? p.owner_name,
      }));
    }
    const seen = new Map<string, DemoPickerItem>();
    for (const p of world.projects) {
      seen.set(p.summary.id, {
        kind: "project",
        id: p.summary.id,
        name: p.summary.name,
        detail: p.summary.owner.name,
      });
    }
    for (const j of adminOpsOf(world).jobs) {
      if (j.project_id && !seen.has(j.project_id)) {
        seen.set(j.project_id, {
          kind: "project",
          id: j.project_id,
          name: j.project_name ?? j.project_id,
          detail: j.user_name || null,
        });
      }
    }
    return [...seen.values()];
  };

  return [
    {
      method: "GET",
      pattern: "/pickers/users",
      handler: (req) => {
        const statuses = enumParam(req, "status", STATUSES);
        if (statuses === null) return invalidQuery();
        const world = getWorld();
        const orgs = adminOrgsOf(world).orgs;
        const notInOrg = queryOne(req, "not_in_org");
        const notInGroup = queryOne(req, "not_in_group");
        const orgMembers = notInOrg
          ? new Set(
              orgs
                .find((o) => o.slug === notInOrg)
                ?.members.map((m) => m.user_id) ?? [],
            )
          : null;
        const groupMembers = notInGroup
          ? new Set(
              orgs.flatMap((o) => o.groups).find((g) => g.id === notInGroup)
                ?.member_ids ?? [],
            )
          : null;
        const rows = adminPeopleOf(world).users.filter(
          (u) =>
            (statuses.length === 0 || statuses.includes(u.status)) &&
            !orgMembers?.has(u.id) &&
            !groupMembers?.has(u.id),
        );
        return pickerList(
          req,
          rows,
          (u) => ({ kind: "user", id: u.id, name: u.name, detail: u.email }),
          (u) => [u.name, u.email],
        );
      },
    },
    {
      method: "GET",
      pattern: "/pickers/orgs",
      handler: (req) =>
        pickerList(
          req,
          adminOrgsOf(getWorld()).orgs,
          (o) => ({ kind: "org", id: o.slug, name: o.name, detail: o.slug }),
          (o) => [o.name, o.slug],
        ),
    },
    {
      method: "GET",
      pattern: "/pickers/projects",
      handler: (req) =>
        pickerList(
          req,
          projects(),
          (p) => p,
          (p) => [p.name, p.detail],
        ),
    },
    {
      method: "GET",
      pattern: "/pickers/runners",
      handler: (req) =>
        pickerList(
          req,
          adminOpsOf(getWorld()).runners.filter((r) => !r.revoked),
          (r) => ({
            kind: "runner",
            id: r.id,
            name: r.name,
            detail: r.version,
          }),
          (r) => [r.name, r.version, ...r.tags],
        ),
    },
  ];
};
