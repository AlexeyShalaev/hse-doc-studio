import { demoError, demoJson, demoNoContent } from "@shared/api/demo";
import type { DemoRoute } from "@shared/api/demo";
import type {
  AccountStatus,
  AdminAuditEvent,
  AdminInvitation,
  AdminUser,
  AdminUserOrg,
  OrgRoleName,
} from "@entities/session";
import type { DemoAdminPeople, DemoAuditEvent } from "./adminPeople";
import {
  boolParam,
  cursorList,
  enumParam,
  hit,
  invalidQuery,
  offsetList,
  queryAll,
  queryOne,
  searchOf,
  timeParam,
  type DemoReq,
} from "./demoList";
import {
  adminInstallOf,
  adminOrgsOf,
  adminPeopleOf,
  type ServerDemoWorld,
} from "./world";

// Демо админки: люди, одобрения, приглашения и журнал. Тела совпадают с contracts/server/fixtures.
//
// Правила, как у настоящего API:
//  - последнего администратора нельзя понизить или отключить (409 last_admin);
//  - удалить можно только отключённый аккаунт без проектов (409 user_not_disabled, user_has_projects);
//  - приглашение на неверный адрес даёт 422 input_invalid, ссылку отдаёт только создание и «новая ссылка».
//
// Списки идут по единому контракту (demoList.ts): поиск, фильтры и сортировка
// на «сервере», журнал листается курсором.

const STATUSES: readonly AccountStatus[] = [
  "active",
  "pending_verification",
  "pending_approval",
  "disabled",
];
const INVITE_STATUSES = ["pending", "used", "expired"] as const;
const ORG_ROLES: readonly OrgRoleName[] = ["owner", "admin", "member"];
type AuditRow = DemoAdminPeople["audit"][number];

/** Журнал сверху вниз: свежие записи, затем архив большого мира по id. */
function* auditRows(people: DemoAdminPeople): Generator<AuditRow> {
  yield* [...people.audit].sort((a, b) => b.id - a.id);
  const archive = people.archive;
  if (!archive) return;
  for (let id = archive.count; id >= 1; id -= 1) yield archive.at(id);
}

/** Состояние приглашения сейчас: просроченное ожидание уже просрочено. */
const inviteStatus = (i: AdminInvitation): AdminInvitation["status"] =>
  i.status === "pending" && Date.parse(i.expires_at) <= Date.now()
    ? "expired"
    : i.status;

const body = (req: { body?: unknown }): Record<string, unknown> =>
  (req.body ?? {}) as Record<string, unknown>;
const notFound = () => demoError(404, "not_found", "Not Found");
const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export const createPeopleRoutes = (
  getWorld: () => ServerDemoWorld,
): DemoRoute[] => {
  const state = () => adminPeopleOf(getWorld());
  // Указатель по id: в большом мире людей двенадцать тысяч, а журнал ищет
  // имя на каждую строку. Пересобирается, когда меняется массив.
  let index: { users: AdminUser[]; byId: Map<string, AdminUser> } | null = null;
  const userOf = (id: string | undefined | null): AdminUser | undefined => {
    const users = state().users;
    if (index?.users !== users || index.byId.size !== users.length) {
      index = { users, byId: new Map(users.map((u) => [u.id, u])) };
    }
    return id ? index.byId.get(id) : undefined;
  };
  /** Люди с фильтрами списка «Люди»; null при неверном параметре. */
  const filteredUsers = (
    req: DemoReq,
    { withStatus = true } = {},
  ): AdminUser[] | null => {
    const statuses = enumParam(req, "status", STATUSES);
    const isAdmin = boolParam(req, "is_admin");
    const org = queryOne(req, "org");
    if (statuses === null || isAdmin === "bad") return null;
    const members = org
      ? new Set(
          adminOrgsOf(getWorld())
            .orgs.find((o) => o.slug === org)
            ?.members.map((m) => m.user_id) ?? [],
        )
      : null;
    return state().users.filter(
      (u) =>
        (!withStatus || statuses.length === 0 || statuses.includes(u.status)) &&
        (isAdmin === null || u.is_instance_admin === isAdmin) &&
        (members === null || members.has(u.id)),
    );
  };
  const USER_SPEC = {
    sort: {
      name: (u: AdminUser) => u.name,
      email: (u: AdminUser) => u.email,
      created_at: (u: AdminUser) => u.created_at,
      last_login_at: (u: AdminUser) => u.last_login_at,
      status: (u: AdminUser) => u.status,
    },
    search: (u: AdminUser) => [u.name, u.email],
    id: (u: AdminUser) => u.id,
  };
  const admins = () =>
    state().users.filter((u) => u.is_instance_admin && u.status === "active")
      .length;
  // Ссылки строятся от публичного адреса установки, как у настоящего сервера.
  const publicUrl = () =>
    adminInstallOf(getWorld()).instance.public_url.replace(/\/+$/, "");
  const linkOf = (id: string) => `${publicUrl()}/invite/demo-${id}`;
  /** Подписи, как у сервера: человек по id, иначе name, label, email или slug из details. */
  const auditView = (e: DemoAuditEvent): AdminAuditEvent => {
    const actor = e.actor_id ? userOf(e.actor_id) : undefined;
    const target = e.target ? userOf(e.target) : undefined;
    const detail = (["name", "label", "email", "slug"] as const)
      .map((key) => e.details[key])
      .find((value): value is string => typeof value === "string");
    return {
      ...e,
      actor: e.actor_id
        ? actor
          ? { id: actor.id, name: actor.name, email: actor.email }
          : { id: e.actor_id, name: e.actor_id, email: null }
        : null,
      target_label: e.target ? (target?.name ?? detail ?? null) : null,
    };
  };
  const record = (action: string, target: string | null) => {
    const events = state().audit;
    events.unshift({
      id: (events[0]?.id ?? 0) + 1,
      at: new Date().toISOString(),
      action,
      actor_id: getWorld().bootstrap.user?.id ?? null,
      target,
      details: {},
    });
  };
  const change =
    (
      action: string,
      apply: (user: AdminUser) => AdminUser | null,
    ): DemoRoute["handler"] =>
    (req) => {
      const user = userOf(req.params.id);
      if (!user) return notFound();
      const next = apply(user);
      if (next === null)
        return demoError(409, "last_admin", "The last administrator");
      Object.assign(user, next);
      record(action, user.id);
      return demoJson(user);
    };

  return [
    {
      method: "GET",
      pattern: "/users",
      handler: (req) => {
        const rows = filteredUsers(req);
        if (rows === null) return invalidQuery();
        return offsetList(req, rows, {
          ...USER_SPEC,
          defaultSort: "-created_at",
        });
      },
    },
    {
      // Числа на чипах под тем же поиском: вместо запроса на каждое состояние.
      method: "GET",
      pattern: "/users/facets",
      handler: (req) => {
        const q = searchOf(req);
        const rows = filteredUsers(req, { withStatus: false });
        if (q === null || rows === null) return invalidQuery();
        const found = rows.filter((u) => hit(q, u.name, u.email));
        const status = Object.fromEntries(
          STATUSES.map((st) => [
            st,
            found.filter((u) => u.status === st).length,
          ]),
        );
        return demoJson({
          status,
          admins: found.filter((u) => u.is_instance_admin).length,
        });
      },
    },
    {
      method: "GET",
      pattern: "/users/:id",
      handler: (req) => {
        const user = userOf(req.params.id);
        return user ? demoJson(user) : notFound();
      },
    },
    {
      // Организации человека: одной ручкой, а не составом каждой организации.
      method: "GET",
      pattern: "/users/:id/orgs",
      handler: (req) => {
        const user = userOf(req.params.id);
        if (!user) return notFound();
        const roles = enumParam(req, "role", ORG_ROLES);
        if (roles === null) return invalidQuery();
        const rows = adminOrgsOf(getWorld()).orgs.flatMap(
          (org): AdminUserOrg[] => {
            const me = org.members.find((m) => m.user_id === user.id);
            if (!me || (roles.length > 0 && !roles.includes(me.role))) {
              return [];
            }
            return [
              {
                slug: org.slug,
                name: org.name,
                role: me.role,
                joined_at: me.joined_at,
              },
            ];
          },
        );
        return offsetList(req, rows, {
          sort: {
            name: (o: AdminUserOrg) => o.name,
            role: (o: AdminUserOrg) => ORG_ROLES.indexOf(o.role),
            joined_at: (o: AdminUserOrg) => o.joined_at,
          },
          defaultSort: "name",
          search: (o) => [o.name, o.slug],
          id: (o) => o.slug,
        });
      },
    },
    {
      method: "PATCH",
      pattern: "/users/:id",
      handler: (req) =>
        change(
          body(req).is_instance_admin === true
            ? "admin.admin_granted"
            : "admin.admin_revoked",
          (user) => {
            const grant = body(req).is_instance_admin === true;
            if (!grant && user.is_instance_admin && admins() <= 1) return null;
            return { ...user, is_instance_admin: grant };
          },
        )(req),
    },
    {
      method: "POST",
      pattern: "/users/:id/disable",
      handler: change("admin.user_disabled", (user) =>
        user.is_instance_admin && admins() <= 1
          ? null
          : { ...user, status: "disabled" },
      ),
    },
    {
      method: "POST",
      pattern: "/users/:id/enable",
      handler: change("admin.user_enabled", (user) => ({
        ...user,
        status: "active",
      })),
    },
    {
      method: "DELETE",
      pattern: "/users/:id",
      handler: (req) => {
        const user = userOf(req.params.id);
        if (!user) return notFound();
        if (user.status !== "disabled")
          return demoError(
            409,
            "user_not_disabled",
            "Disable the account first",
          );
        if (user.project_count > 0)
          return demoError(409, "user_has_projects", "The user owns projects");
        state().users = state().users.filter((u) => u.id !== user.id);
        record("admin.user_deleted", user.id);
        return demoNoContent();
      },
    },
    {
      method: "POST",
      pattern: "/users/:id/reset-link",
      handler: (req) => {
        const user = userOf(req.params.id);
        if (!user) return notFound();
        if (body(req).confirm !== true)
          return demoError(403, "forbidden", "Confirmation is required");
        record("admin.reset_link_issued", user.id);
        return demoJson({
          link: `${publicUrl()}/reset/demo-${user.id}`,
          expires_at: new Date(Date.now() + 3_600_000).toISOString(),
          user_notified: false,
        });
      },
    },
    {
      method: "POST",
      pattern: "/users/:id/sessions/revoke",
      handler: (req) => {
        const user = userOf(req.params.id);
        if (!user) return notFound();
        record("admin.sessions_revoked", user.id);
        return demoJson({ revoked: user.last_login_at ? 2 : 0 });
      },
    },
    {
      method: "GET",
      pattern: "/approvals",
      handler: (req) =>
        offsetList(
          req,
          state().users.filter((u) => u.status === "pending_approval"),
          {
            sort: {
              created_at: USER_SPEC.sort.created_at,
              name: USER_SPEC.sort.name,
              email: USER_SPEC.sort.email,
            },
            // Старые заявки первыми: они ждут дольше всех.
            defaultSort: "created_at",
            search: USER_SPEC.search,
            id: USER_SPEC.id,
          },
        ),
    },
    {
      method: "POST",
      pattern: "/approvals/:id/approve",
      handler: change("admin.user_approved", (user) => ({
        ...user,
        status: "active",
      })),
    },
    {
      method: "POST",
      pattern: "/approvals/:id/reject",
      handler: change("admin.user_rejected", (user) => ({
        ...user,
        status: "disabled",
      })),
    },
    {
      method: "GET",
      pattern: "/invitations",
      handler: (req) => {
        const statuses = enumParam(req, "status", INVITE_STATUSES);
        if (statuses === null) return invalidQuery();
        const org = queryOne(req, "org");
        const orgOf = state().invitationOrgs;
        const rows = state()
          .invitations.map((i) => ({ ...i, status: inviteStatus(i) }))
          .filter(
            (i) =>
              (statuses.length === 0 || statuses.includes(i.status)) &&
              (org === null || orgOf?.get(i.id) === org),
          );
        return offsetList(req, rows, {
          sort: {
            expires_at: (i: AdminInvitation) => i.expires_at,
            email: (i: AdminInvitation) => i.email,
          },
          defaultSort: "-expires_at",
          search: (i) => [i.email],
          id: (i) => i.id,
        });
      },
    },
    {
      method: "POST",
      pattern: "/invitations",
      handler: (req) => {
        const raw = body(req).email;
        const email = typeof raw === "string" && raw.trim() ? raw.trim() : null;
        if (email !== null && !EMAIL.test(email))
          return demoError(422, "input_invalid", "Invalid input");
        const days = Number(body(req).ttl_days) || 7;
        const invitation: AdminInvitation = {
          id: `inv_${Math.random().toString(36).slice(2, 8)}`,
          email,
          status: "pending",
          expires_at: new Date(Date.now() + days * 86_400_000).toISOString(),
          used_at: null,
        };
        state().invitations.unshift(invitation);
        return demoJson({ invitation, link: linkOf(invitation.id) }, 201);
      },
    },
    {
      method: "POST",
      pattern: "/invitations/:id/resend",
      handler: (req) => {
        const invitation = state().invitations.find(
          (i) => i.id === req.params.id,
        );
        if (!invitation) return notFound();
        if (invitation.status === "used")
          return demoError(404, "not_found", "Not Found");
        invitation.status = "pending";
        invitation.expires_at = new Date(
          Date.now() + 7 * 86_400_000,
        ).toISOString();
        record("admin.invite_resent", invitation.id);
        return demoJson({ invitation, link: linkOf(invitation.id) });
      },
    },
    {
      method: "DELETE",
      pattern: "/invitations/:id",
      handler: (req) => {
        const before = state().invitations.length;
        state().invitations = state().invitations.filter(
          (i) => i.id !== req.params.id,
        );
        return state().invitations.length === before
          ? notFound()
          : demoNoContent();
      },
    },
    {
      method: "GET",
      pattern: "/audit",
      handler: (req) => {
        const q = searchOf(req);
        const from = timeParam(req, "from", "since");
        const to = timeParam(req, "to", "until");
        if (q === null || from === "bad" || to === "bad") return invalidQuery();
        const categories = queryAll(req, "category").map((c) => `${c}.`);
        // Прежний клиент слал префикс в action («auth.»): он тоже категория.
        const actions = queryAll(req, "action");
        const prefixes = [
          ...categories,
          ...actions.filter((a) => a.endsWith(".")),
        ];
        const exact = actions.filter((a) => !a.endsWith("."));
        const actor = queryOne(req, "actor_id");
        const target = queryOne(req, "target");
        // Поиск по людям: не больше 200 подходящих по имени или почте.
        const actors = q
          ? new Set(
              state()
                .users.filter((u) => hit(q, u.name, u.email))
                .slice(0, 200)
                .map((u) => u.id),
            )
          : null;
        const filtered =
          q !== "" ||
          from !== null ||
          to !== null ||
          prefixes.length > 0 ||
          exact.length > 0 ||
          actor !== null ||
          target !== null;
        const people = state();
        return cursorList(req, auditRows(people), (e) => e.id, {
          accept: (e) => {
            const at = Date.parse(e.at);
            return (
              (from === null || at >= from) &&
              (to === null || at < to) &&
              (prefixes.length === 0 ||
                prefixes.some((p) => e.action.startsWith(p))) &&
              (exact.length === 0 || exact.includes(e.action)) &&
              (actor === null || e.actor_id === actor) &&
              (target === null || e.target === target) &&
              (q === "" ||
                hit(q, e.action, e.target) ||
                (e.actor_id !== null && (actors?.has(e.actor_id) ?? false)))
            );
          },
          view: auditView,
          totalEstimate: filtered
            ? null
            : people.audit.length + (people.archive?.count ?? 0),
        });
      },
    },
  ];
};
