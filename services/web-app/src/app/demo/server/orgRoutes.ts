import { demoError, demoJson, demoNoContent } from "@shared/api/demo";
import type { DemoResponse, DemoRoute } from "@shared/api/demo";
import type {
  AdminGroup,
  AdminGroupMember,
  AdminOrg,
  AdminOrgMember,
  AdminUserOrg,
  OrgRoleName,
} from "@entities/session";
import type { DemoGroup, DemoOrg } from "./adminOrgs";
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

const ROLES: readonly OrgRoleName[] = ["owner", "admin", "member"];
const RESERVED = ["admin", "api", "auth", "account", "orgs", "new"];
const SLUG = /^[a-z0-9]+(-[a-z0-9]+)*$/;

const str = (value: unknown): string =>
  typeof value === "string" ? value : "";
const isRole = (value: unknown): value is OrgRoleName =>
  ROLES.includes(value as OrgRoleName);

const notFound = () => demoError(404, "not_found", "Not Found");

type DemoReq = Parameters<DemoRoute["handler"]>[0];
const queryText = (value: string | string[] | undefined): string =>
  (Array.isArray(value) ? value[0] : value) ?? "";
const queryList = (value: string | string[] | undefined): string[] =>
  value === undefined ? [] : Array.isArray(value) ? value : [value];

/** Страница списка, как у сервера: поиск подстроки без учёта регистра, limit (до 200) и offset. */
const pageOf = <T>(
  items: readonly T[],
  req: DemoReq,
  text: (item: T) => string,
) => {
  const q = queryText(req.query.q).trim().toLowerCase();
  const found = q
    ? items.filter((x) => text(x).toLowerCase().includes(q))
    : [...items];
  const limit = Math.min(Number(queryText(req.query.limit)) || 50, 200);
  const offset = Number(queryText(req.query.offset)) || 0;
  return {
    items: found.slice(offset, offset + limit),
    total: found.length,
    limit,
    offset,
  };
};

const ROLE_ORDER: readonly OrgRoleName[] = ["owner", "admin", "member"];
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

  const summary = (org: DemoOrg): AdminOrg => ({
    slug: org.slug,
    name: org.name,
    member_count: org.members.length,
    project_count: org.project_count,
    owner_count: org.members.filter((m) => m.role === "owner").length,
    my_role: roleIn(org),
  });

  /** Группа наружу: число участников и первые пять по имени. */
  const groupOf = (org: DemoOrg, group: DemoGroup): AdminGroup => {
    const people = org.members
      .filter((m) => group.member_ids.includes(m.user_id))
      .sort((a, b) => a.name.localeCompare(b.name));
    return {
      id: group.id,
      name: group.name,
      member_count: people.length,
      preview: people
        .slice(0, 5)
        .map((m) => ({ user_id: m.user_id, name: m.name })),
    };
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

  const owners = (org: DemoOrg): number =>
    org.members.filter((m) => m.role === "owner").length;

  const body = (req: { body?: unknown }): Record<string, unknown> =>
    (req.body ?? {}) as Record<string, unknown>;

  const newId = (prefix: string): string =>
    `${prefix}_${Math.random().toString(36).slice(2, 12)}`;

  return [
    {
      method: "GET",
      pattern: "/orgs",
      handler: guarded((req) =>
        demoJson(
          pageOf(
            state()
              .orgs.filter(manages)
              .map(summary)
              .sort((a, b) => a.name.localeCompare(b.name)),
            req,
            (o) => `${o.name} ${o.slug}`,
          ),
        ),
      ),
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
        const roles = queryList(req.query.role);
        const shown = roles.length
          ? org.members.filter((m) => roles.includes(m.role))
          : org.members;
        return demoJson(pageOf(shown, req, (m) => `${m.name} ${m.email}`));
      }),
    },
    {
      method: "GET",
      pattern: "/orgs/:slug/members/facets",
      handler: withOrg((org, req) => {
        const q = queryText(req.query.q).trim().toLowerCase();
        const found = org.members.filter((m) =>
          `${m.name} ${m.email}`.toLowerCase().includes(q),
        );
        const role = Object.fromEntries(
          ROLE_ORDER.map((r) => [r, found.filter((m) => m.role === r).length]),
        ) as Record<OrgRoleName, number>;
        return demoJson({ role });
      }),
    },
    {
      method: "POST",
      pattern: "/orgs/:slug/members",
      handler: withOrg((org, req) => {
        const b = body(req);
        const email = str(b.email).trim().toLowerCase();
        const userId = str(b.user_id);
        if ((email === "") === (userId === "") || !isRole(b.role)) {
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
        return demoJson(added, 201);
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
        return demoJson(next);
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
        demoJson(
          pageOf(
            org.groups
              .map((g) => groupOf(org, g))
              .sort((a, b) => a.name.localeCompare(b.name)),
            req,
            (g) => g.name,
          ),
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
        const group: DemoGroup = {
          id: newId("g"),
          name,
          member_ids: memberIds,
        };
        org.groups = [...org.groups, group];
        return demoJson(groupOf(org, group), 201);
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
        return demoJson(groupOf(org, next));
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
    {
      method: "GET",
      pattern: "/orgs/:slug/groups/:id/members",
      handler: withOrg((org, req) => {
        const group = org.groups.find((g) => g.id === req.params.id);
        if (!group) return notFound();
        const people: AdminGroupMember[] = org.members
          .filter((m) => group.member_ids.includes(m.user_id))
          .sort((a, b) => a.name.localeCompare(b.name))
          .map((m) => ({
            user_id: m.user_id,
            name: m.name,
            email: m.email,
            added_at: m.joined_at,
          }));
        return demoJson(pageOf(people, req, (m) => `${m.name} ${m.email}`));
      }),
    },
    {
      method: "POST",
      pattern: "/orgs/:slug/groups/:id/members/:userId",
      handler: withOrg((org, req) => {
        const group = org.groups.find((g) => g.id === req.params.id);
        if (!group) return notFound();
        const person = org.members.find((m) => m.user_id === req.params.userId);
        if (!person) return invalid();
        if (group.member_ids.includes(person.user_id)) {
          return demoError(409, "already_member", "Already a member");
        }
        group.member_ids = [...group.member_ids, person.user_id];
        const added: AdminGroupMember = {
          user_id: person.user_id,
          name: person.name,
          email: person.email,
          added_at: new Date().toISOString().replace(/\.\d+Z$/, "Z"),
        };
        return demoJson(added, 201);
      }),
    },
    {
      method: "DELETE",
      pattern: "/orgs/:slug/groups/:id/members/:userId",
      handler: withOrg((org, req) => {
        const group = org.groups.find((g) => g.id === req.params.id);
        if (!group?.member_ids.includes(req.params.userId ?? "")) {
          return notFound();
        }
        group.member_ids = group.member_ids.filter(
          (id) => id !== req.params.userId,
        );
        return demoNoContent();
      }),
    },
    {
      method: "GET",
      pattern: "/users/:id/orgs",
      handler: guarded((req) => {
        const items: AdminUserOrg[] = state().orgs.flatMap((org) => {
          const me = org.members.find((m) => m.user_id === req.params.id);
          return me
            ? [
                {
                  slug: org.slug,
                  name: org.name,
                  role: me.role,
                  joined_at: me.joined_at,
                },
              ]
            : [];
        });
        items.sort((a, b) => a.name.localeCompare(b.name));
        return demoJson(pageOf(items, req, (o) => `${o.name} ${o.slug}`));
      }),
    },
  ];
};
