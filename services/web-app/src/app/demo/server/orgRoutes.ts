import { demoError, demoJson, demoNoContent } from "@shared/api/demo";
import type { DemoResponse, DemoRoute } from "@shared/api/demo";
import type {
  AdminGroup,
  AdminGroupMember,
  AdminOrg,
  AdminOrgMember,
  OrgRoleName,
} from "@entities/session";
import type { DemoGroup, DemoOrg } from "./adminOrgs";
import {
  boolParam,
  enumParam,
  hit,
  invalidQuery,
  offsetList,
  searchOf,
} from "./demoList";
import { adminOrgsOf, type ServerDemoWorld } from "./world";

// Демо админки: организации, участники и группы. Тела совпадают с contracts/server/fixtures.
//
// Правила, как у настоящего API:
//  - админ установки видит все организации, админ организации (owner, admin) только свои, остальным 404;
//  - организацию создаёт и удаляет только админ установки, создатель становится владельцем;
//  - организацию с проектами удалить нельзя (409 org_has_projects);
//  - последнего владельца не понизить и не убрать (409 last_owner);
//  - админ организации не трогает владельцев и не назначает владельцев (403 forbidden).
//
// Особые значения: адрес участника, которого нет среди людей установки, даёт 404;
// адрес организации admin, api, auth, account зарезервирован.
//
// Списки идут по единому контракту (demoList.ts): поиск, фильтры, сортировка и
// страницы; без limit в запросе прежний массив. Строка участника несёт
// is_last_owner, организация owner_count; группа отдаёт число участников и
// первых пятерых, состав листается .../groups/{id}/members и меняется точечно.

const ROLES: readonly OrgRoleName[] = ["owner", "admin", "member"];
const RESERVED = ["admin", "api", "auth", "account", "orgs", "new"];
const SLUG = /^[a-z0-9]+(-[a-z0-9]+)*$/;

const str = (value: unknown): string =>
  typeof value === "string" ? value : "";
const isRole = (value: unknown): value is OrgRoleName =>
  ROLES.includes(value as OrgRoleName);

const notFound = () => demoError(404, "not_found", "Not Found");
const forbidden = () => demoError(403, "forbidden", "Forbidden");
const invalid = () => demoError(422, "input_invalid", "Invalid input");

export const createOrgRoutes = (
  getWorld: () => ServerDemoWorld,
): DemoRoute[] => {
  const state = () => adminOrgsOf(getWorld());
  const viewer = () => getWorld().bootstrap.user;
  const roleIn = (org: DemoOrg): OrgRoleName | null =>
    org.members.find((m) => m.user_id === viewer()?.id)?.role ?? null;
  const manages = (org: DemoOrg): boolean => {
    if (viewer()?.is_instance_admin) return true;
    const role = roleIn(org);
    return role === "owner" || role === "admin";
  };
  /** Владелец и админ установки распоряжаются всем, админ организации только рядовыми. */
  const isFull = (org: DemoOrg): boolean =>
    viewer()?.is_instance_admin === true || roleIn(org) === "owner";

  const owners = (org: DemoOrg): number =>
    org.members.filter((m) => m.role === "owner").length;

  const summary = (org: DemoOrg): AdminOrg => ({
    slug: org.slug,
    name: org.name,
    member_count: org.members.length,
    project_count: org.project_count,
    my_role: roleIn(org),
    owner_count: owners(org),
  });

  /** Группа наружу: число участников и первые пять по имени. */
  const groupView = (org: DemoOrg, group: DemoGroup): AdminGroup => {
    const ids = new Set(group.member_ids);
    const people = org.members
      .filter((m) => ids.has(m.user_id))
      .sort((a, b) => a.name.localeCompare(b.name, "ru"));
    return {
      id: group.id,
      name: group.name,
      member_count: people.length,
      preview: people
        .slice(0, 5)
        .map((m) => ({ user_id: m.user_id, name: m.name })),
    };
  };

  /** Участник группы: имя и почта из организации, время добавления. */
  const groupMembers = (org: DemoOrg, group: DemoGroup): AdminGroupMember[] => {
    const ids = new Set(group.member_ids);
    return org.members
      .filter((m) => ids.has(m.user_id))
      .map((m) => ({
        user_id: m.user_id,
        name: m.name,
        email: m.email,
        added_at: group.added_at?.[m.user_id] ?? m.joined_at,
      }));
  };

  const memberView = (org: DemoOrg) => {
    const ownerTotal = owners(org);
    return (m: AdminOrgMember): AdminOrgMember => ({
      ...m,
      is_last_owner: m.role === "owner" && ownerTotal === 1,
    });
  };

  const guard = (): DemoResponse | null => {
    const user = viewer();
    if (user === null)
      return demoError(401, "auth_required", "Authentication required");
    return user.is_instance_admin || state().orgs.some(manages)
      ? null
      : notFound();
  };

  const guarded =
    (handler: DemoRoute["handler"]): DemoRoute["handler"] =>
    (req) =>
      guard() ?? handler(req);

  /** Организация по адресу; чужая и несуществующая выглядят одинаково. */
  const withOrg = (
    handler: (
      org: DemoOrg,
      req: Parameters<DemoRoute["handler"]>[0],
    ) => DemoResponse,
  ): DemoRoute["handler"] =>
    guarded((req) => {
      const org = state().orgs.find((o) => o.slug === req.params.slug);
      return org && manages(org) ? handler(org, req) : notFound();
    });

  const body = (req: { body?: unknown }): Record<string, unknown> =>
    (req.body ?? {}) as Record<string, unknown>;

  const newId = (prefix: string): string =>
    `${prefix}_${Math.random().toString(36).slice(2, 12)}`;

  return [
    {
      method: "GET",
      pattern: "/orgs",
      handler: guarded((req) => {
        const mine = boolParam(req, "mine");
        if (mine === "bad") return invalidQuery();
        const rows = state()
          .orgs.filter(manages)
          .filter((o) => mine === null || (roleIn(o) !== null) === mine)
          .map(summary);
        return offsetList(
          req,
          rows,
          {
            sort: {
              name: (o: AdminOrg) => o.name,
              slug: (o: AdminOrg) => o.slug,
              member_count: (o: AdminOrg) => o.member_count,
              project_count: (o: AdminOrg) => o.project_count,
            },
            defaultSort: "name",
            search: (o) => [o.name, o.slug],
            id: (o) => o.slug,
          },
          { legacyArray: true },
        );
      }),
    },
    {
      method: "POST",
      pattern: "/orgs",
      handler: guarded((req) => {
        const user = viewer();
        if (!user?.is_instance_admin) return forbidden();
        const b = body(req);
        const name = str(b.name).trim();
        const slug = str(b.slug).trim();
        if (name === "" || name.length > 80) return invalid();
        if (!SLUG.test(slug) || slug.length > 40) {
          return demoError(422, "slug_invalid", "Invalid slug");
        }
        if (RESERVED.includes(slug)) {
          return demoError(422, "slug_reserved", "Reserved slug");
        }
        if (state().orgs.some((o) => o.slug === slug)) {
          return demoError(409, "slug_taken", "Slug is taken");
        }
        const me = state().directory.find((u) => u.id === user.id);
        const org: DemoOrg = {
          slug,
          name,
          project_count: 0,
          members: me
            ? [
                {
                  user_id: me.id,
                  name: me.name,
                  email: me.email,
                  role: "owner",
                  joined_at: new Date().toISOString().replace(/\.\d+Z$/, "Z"),
                },
              ]
            : [],
          groups: [],
        };
        state().orgs = [...state().orgs, org];
        return demoJson(summary(org), 201);
      }),
    },
    {
      method: "GET",
      pattern: "/orgs/:slug",
      handler: withOrg((org) => demoJson(summary(org))),
    },
    {
      method: "DELETE",
      pattern: "/orgs/:slug",
      handler: withOrg((org) => {
        if (!viewer()?.is_instance_admin) return forbidden();
        if (org.project_count > 0) {
          return demoError(
            409,
            "org_has_projects",
            "Organization has projects",
          );
        }
        state().orgs = state().orgs.filter((o) => o !== org);
        return demoNoContent();
      }),
    },

    {
      method: "GET",
      pattern: "/orgs/:slug/members",
      handler: withOrg((org, req) => {
        const roles = enumParam(req, "role", ROLES);
        if (roles === null) return invalidQuery();
        const rank = (m: AdminOrgMember) => ROLES.indexOf(m.role);
        return offsetList(
          req,
          roles.length
            ? org.members.filter((m) => roles.includes(m.role))
            : org.members,
          {
            sort: {
              name: (m: AdminOrgMember) => m.name,
              email: (m: AdminOrgMember) => m.email,
              role: rank,
              joined_at: (m: AdminOrgMember) => m.joined_at,
            },
            defaultSort: "joined_at",
            search: (m) => [m.name, m.email],
            id: (m) => m.user_id,
          },
          { legacyArray: true, view: memberView(org) },
        );
      }),
    },
    {
      // Числа на чипах ролей под тем же поиском.
      method: "GET",
      pattern: "/orgs/:slug/members/facets",
      handler: withOrg((org, req) => {
        const q = searchOf(req);
        if (q === null) return invalidQuery();
        const found = org.members.filter((m) => hit(q, m.name, m.email));
        return demoJson({
          role: Object.fromEntries(
            ROLES.map((r) => [r, found.filter((m) => m.role === r).length]),
          ),
        });
      }),
    },
    {
      method: "POST",
      pattern: "/orgs/:slug/members",
      handler: withOrg((org, req) => {
        const b = body(req);
        // Человек из пикера приходит по id, запасной путь по почте.
        const userId = str(b.user_id).trim();
        const email = str(b.email).trim().toLowerCase();
        if ((email === "" && userId === "") || !isRole(b.role)) {
          return invalid();
        }
        if (b.role === "owner" && !isFull(org)) return forbidden();
        const person = state().directory.find((u) =>
          userId ? u.id === userId : u.email === email,
        );
        if (!person) return notFound();
        if (org.members.some((m) => m.user_id === person.id)) {
          return demoError(409, "already_member", "Already a member");
        }
        const added: AdminOrgMember = {
          user_id: person.id,
          name: person.name,
          email: person.email,
          role: b.role,
          joined_at: new Date().toISOString().replace(/\.\d+Z$/, "Z"),
        };
        org.members = [...org.members, added];
        return demoJson(memberView(org)(added), 201);
      }),
    },
    {
      method: "PATCH",
      pattern: "/orgs/:slug/members/:userId",
      handler: withOrg((org, req) => {
        const current = org.members.find(
          (m) => m.user_id === req.params.userId,
        );
        if (!current) return notFound();
        const role = body(req).role;
        if (!isRole(role)) return invalid();
        if (!isFull(org) && (current.role === "owner" || role === "owner")) {
          return forbidden();
        }
        if (current.role === "owner" && role !== "owner" && owners(org) === 1) {
          return demoError(
            409,
            "last_owner",
            "The last owner cannot be changed",
          );
        }
        const next = { ...current, role };
        org.members = org.members.map((m) => (m === current ? next : m));
        return demoJson(memberView(org)(next));
      }),
    },
    {
      method: "DELETE",
      pattern: "/orgs/:slug/members/:userId",
      handler: withOrg((org, req) => {
        const current = org.members.find(
          (m) => m.user_id === req.params.userId,
        );
        if (!current) return notFound();
        if (!isFull(org) && current.role === "owner") return forbidden();
        if (current.role === "owner" && owners(org) === 1) {
          return demoError(
            409,
            "last_owner",
            "The last owner cannot be removed",
          );
        }
        org.members = org.members.filter((m) => m !== current);
        // Ушедший человек уходит и из групп.
        org.groups = org.groups.map((g) => ({
          ...g,
          member_ids: g.member_ids.filter((id) => id !== current.user_id),
        }));
        return demoNoContent();
      }),
    },

    {
      method: "GET",
      pattern: "/orgs/:slug/groups",
      handler: withOrg((org, req) =>
        offsetList(
          req,
          org.groups,
          {
            sort: {
              name: (g: DemoGroup) => g.name,
              member_count: (g: DemoGroup) => g.member_ids.length,
            },
            defaultSort: "name",
            search: (g) => [g.name],
            id: (g) => g.id,
          },
          { legacyArray: true, view: (g) => groupView(org, g) },
        ),
      ),
    },
    {
      method: "POST",
      pattern: "/orgs/:slug/groups",
      handler: withOrg((org, req) => {
        const b = body(req);
        const name = str(b.name).trim();
        const ids = b.member_ids;
        if (name === "" || name.length > 80) return invalid();
        if (!Array.isArray(ids)) return invalid();
        const memberIds = [...new Set(ids.map(str))];
        if (
          !memberIds.every((id) => org.members.some((m) => m.user_id === id))
        ) {
          return invalid();
        }
        const now = new Date().toISOString().replace(/\.\d+Z$/, "Z");
        const group: DemoGroup = {
          id: newId("g"),
          name,
          member_ids: memberIds,
          added_at: Object.fromEntries(memberIds.map((id) => [id, now])),
        };
        org.groups = [...org.groups, group];
        return demoJson(groupView(org, group), 201);
      }),
    },
    {
      method: "PATCH",
      pattern: "/orgs/:slug/groups/:id",
      handler: withOrg((org, req) => {
        const current = org.groups.find((g) => g.id === req.params.id);
        if (!current) return notFound();
        const b = body(req);
        const next = { ...current };
        if (b.name != null) {
          const name = str(b.name).trim();
          if (name === "" || name.length > 80) return invalid();
          next.name = name;
        }
        if (b.member_ids != null) {
          if (!Array.isArray(b.member_ids)) return invalid();
          const ids = [...new Set(b.member_ids.map(str))];
          if (!ids.every((id) => org.members.some((m) => m.user_id === id))) {
            return invalid();
          }
          next.member_ids = ids;
        }
        org.groups = org.groups.map((g) => (g === current ? next : g));
        return demoJson(groupView(org, next));
      }),
    },
    {
      method: "GET",
      pattern: "/orgs/:slug/groups/:id/members",
      handler: withOrg((org, req) => {
        const group = org.groups.find((g) => g.id === req.params.id);
        if (!group) return notFound();
        return offsetList(req, groupMembers(org, group), {
          sort: {
            name: (m: AdminGroupMember) => m.name,
            email: (m: AdminGroupMember) => m.email,
            added_at: (m: AdminGroupMember) => m.added_at,
          },
          defaultSort: "name",
          search: (m) => [m.name, m.email],
          id: (m) => m.user_id,
        });
      }),
    },
    {
      // Состав меняется по одному человеку: полный member_ids не нужен.
      method: "POST",
      pattern: "/orgs/:slug/groups/:id/members/:userId",
      handler: withOrg((org, req) => {
        const group = org.groups.find((g) => g.id === req.params.id);
        const userId = req.params.userId ?? "";
        if (!group) return notFound();
        const member = org.members.find((m) => m.user_id === userId);
        if (!member) return notFound();
        if (group.member_ids.includes(userId)) {
          return demoError(409, "already_member", "Already a member");
        }
        const now = new Date().toISOString().replace(/\.\d+Z$/, "Z");
        group.member_ids = [...group.member_ids, userId];
        group.added_at = { ...group.added_at, [userId]: now };
        return demoJson(
          {
            user_id: member.user_id,
            name: member.name,
            email: member.email,
            added_at: now,
          },
          201,
        );
      }),
    },
    {
      method: "DELETE",
      pattern: "/orgs/:slug/groups/:id/members/:userId",
      handler: withOrg((org, req) => {
        const group = org.groups.find((g) => g.id === req.params.id);
        const userId = req.params.userId ?? "";
        if (!group?.member_ids.includes(userId)) return notFound();
        group.member_ids = group.member_ids.filter((id) => id !== userId);
        return demoNoContent();
      }),
    },
    {
      method: "DELETE",
      pattern: "/orgs/:slug/groups/:id",
      handler: withOrg((org, req) => {
        if (!org.groups.some((g) => g.id === req.params.id)) return notFound();
        org.groups = org.groups.filter((g) => g.id !== req.params.id);
        return demoNoContent();
      }),
    },
  ];
};
