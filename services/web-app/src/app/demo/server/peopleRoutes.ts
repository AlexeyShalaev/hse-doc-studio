import { demoError, demoJson, demoNoContent } from "@shared/api/demo";
import type { DemoRoute } from "@shared/api/demo";
import type { AdminInvitation, AdminUser } from "@entities/session";
import { adminInstallOf, adminPeopleOf, type ServerDemoWorld } from "./world";

// Демо админки: люди, одобрения, приглашения и журнал. Тела совпадают с contracts/server/fixtures.
//
// Правила, как у настоящего API:
//  - последнего администратора нельзя понизить или отключить (409 last_admin);
//  - удалить можно только отключённый аккаунт без проектов (409 user_not_disabled, user_has_projects);
//  - приглашение на неверный адрес даёт 422 input_invalid, ссылку отдаёт только создание и «новая ссылка».

const PAGE = 25;
const body = (req: { body?: unknown }): Record<string, unknown> =>
  (req.body ?? {}) as Record<string, unknown>;
const notFound = () => demoError(404, "not_found", "Not Found");
const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

const queryText = (value: string | string[] | undefined): string =>
  (Array.isArray(value) ? value[0] : value) ?? "";

export const createPeopleRoutes = (
  getWorld: () => ServerDemoWorld,
): DemoRoute[] => {
  const state = () => adminPeopleOf(getWorld());
  const userOf = (id: string | undefined): AdminUser | undefined =>
    state().users.find((u) => u.id === id);
  const admins = () =>
    state().users.filter((u) => u.is_instance_admin && u.status === "active")
      .length;
  const page = <T>(items: T[], req: Parameters<DemoRoute["handler"]>[0]) => {
    const limit = Number(queryText(req.query.limit)) || PAGE;
    const offset = Number(queryText(req.query.offset)) || 0;
    return {
      items: items.slice(offset, offset + limit),
      total: items.length,
      limit,
      offset,
    };
  };
  // Ссылки строятся от публичного адреса установки, как у настоящего сервера.
  const publicUrl = () =>
    adminInstallOf(getWorld()).instance.public_url.replace(/\/+$/, "");
  const linkOf = (id: string) => `${publicUrl()}/invite/demo-${id}`;
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
        const q = queryText(req.query.q).trim().toLowerCase();
        const status = queryText(req.query.status);
        const found = state().users.filter(
          (u) =>
            (status === "" || u.status === status) &&
            (q === "" ||
              u.name.toLowerCase().includes(q) ||
              u.email.toLowerCase().includes(q)),
        );
        return demoJson(page(found, req));
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
        demoJson(
          page(
            state().users.filter((u) => u.status === "pending_approval"),
            req,
          ),
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
      handler: (req) => demoJson(page(state().invitations, req)),
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
        const prefix = queryText(req.query.action);
        const before = Number(queryText(req.query.cursor)) || Infinity;
        const limit = Number(queryText(req.query.limit)) || PAGE;
        const found = state().audit.filter(
          (e) =>
            e.id < before && (prefix === "" || e.action.startsWith(prefix)),
        );
        const items = found.slice(0, limit);
        const last = items[items.length - 1];
        return demoJson({
          items,
          next_cursor: found.length > limit && last ? String(last.id) : null,
        });
      },
    },
  ];
};
