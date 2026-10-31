import { demoError, demoJson, demoNoContent } from "@shared/api/demo";
import type { DemoRequest, DemoResponse, DemoRoute } from "@shared/api/demo";
import type { GrantRole, ProjectInvitation } from "@entities/invitation";
import { effectiveRole } from "./projectAccess";
import type { DemoProject } from "./projects";
import { adminOrgsOf, type ServerDemoWorld } from "./world";
import { invitesOf, nextId, type DemoInvites } from "./invitations";

// Демо маршрутов трека invites (раздел 8.2): те же коды, что у сервера. Приглашать и решать запросы может
// владелец; передавать проект только владелец; чужой проект это 404.

const notFound = () => demoError(404, "not_found", "Not Found");
const now = () => new Date().toISOString();
const DAY = 86_400_000;
const ROLES: readonly GrantRole[] = ["reader", "reviewer", "editor"];

type Body = Record<string, unknown>;
const bodyOf = (req: DemoRequest): Body => (req.body ?? {}) as Body;
const str = (v: unknown): string | null =>
  typeof v === "string" && v.trim() !== "" ? v.trim() : null;

export const createInvitationRoutes = (
  getWorld: () => ServerDemoWorld,
): DemoRoute[] => {
  const signedIn =
    (
      handler: (
        req: DemoRequest,
        world: ServerDemoWorld,
        state: DemoInvites,
        userId: string,
      ) => DemoResponse,
    ): DemoRoute["handler"] =>
    (req) => {
      const world = getWorld();
      const user = world.bootstrap.user;
      if (!user)
        return demoError(401, "auth_required", "Authentication required");
      return handler(req, world, invitesOf(world), user.id);
    };

  const project = (
    need: "view" | "manage",
    handler: (
      req: DemoRequest,
      p: DemoProject,
      state: DemoInvites,
      world: ServerDemoWorld,
    ) => DemoResponse,
  ): DemoRoute["handler"] =>
    signedIn((req, world, state, userId) => {
      const p = world.projects.find(
        (x) => x.summary.id === req.params.projectId,
      );
      const role = p ? effectiveRole(world, p, userId) : null;
      if (!p || !role) return notFound();
      if (need === "manage" && role !== "owner") {
        return demoError(403, "forbidden", "Forbidden");
      }
      return handler(req, p, state, world);
    });

  const listOf = (state: DemoInvites, id: string) =>
    (state.projectInvitations[id] ??= []);
  const requestsOf = (state: DemoInvites, id: string) =>
    (state.projectRequests[id] ??= []);
  const page = (items: readonly unknown[]) =>
    demoJson({ items, total: items.length, limit: 50, offset: 0 });

  return [
    {
      method: "GET",
      pattern: "/projects/:projectId/invitations",
      handler: project("manage", (req, p, state) => {
        const all = req.query.status === "all";
        const items = listOf(state, p.summary.id).filter(
          (i) => all || i.status === "pending" || i.status === "expired",
        );
        return page(items);
      }),
    },
    {
      method: "POST",
      pattern: "/projects/:projectId/invitations",
      handler: project("manage", (req, p, state, world) => {
        const body = bodyOf(req);
        const role = body.role as GrantRole;
        if (!ROLES.includes(role)) {
          return demoError(422, "input_invalid", "Invalid input");
        }
        const userId = str(body.user_id);
        const email = str(body.email);
        const person = userId
          ? adminOrgsOf(world).directory.find((u) => u.id === userId)
          : undefined;
        if (userId && !person) return notFound();
        if (userId && p.roles[userId]) {
          return demoError(409, "already_member", "Already a member");
        }
        if (email === "closed@example.org") {
          return demoError(409, "invitee_cannot_register", "Cannot register");
        }
        const list = listOf(state, p.summary.id);
        const twin = list.find(
          (i) =>
            i.status === "pending" &&
            (i.invitee.user_id === userId ||
              (email !== null && i.invitee.email_hint === email)),
        );
        if (twin) {
          return demoError(409, "invitation_pending", "Pending", {
            invitation_id: twin.id,
          });
        }
        // Просроченное ожидающее место не держит: его заменяет новое, как на сервере.
        for (const old of list) {
          if (
            old.status === "expired" &&
            (old.invitee.user_id === userId ||
              (email !== null && old.invitee.email_hint === email))
          ) {
            old.status = "revoked";
          }
        }
        const days = Number(body.expires_in_days ?? 7);
        const user = world.bootstrap.user;
        const inv: ProjectInvitation = {
          id: nextId(state, "inv"),
          invitee: person
            ? {
                kind: "user",
                user_id: person.id,
                name: person.name,
                email_hint: null,
              }
            : { kind: "email", user_id: null, name: null, email_hint: email },
          role,
          persona: str(body.persona),
          can_share: body.can_share === true,
          show_sources: body.show_sources !== false,
          can_edit_all: body.can_edit_all === true,
          message: str(body.message),
          invited_by: user ? { id: user.id, name: user.name } : null,
          created_at: now(),
          expires_at: new Date(Date.now() + days * DAY).toISOString(),
          status: "pending",
          sent_count: 1,
          last_sent_at: now(),
        };
        list.unshift(inv);
        const smtp = world.bootstrap.auth.smtp_enabled;
        if (person) {
          return demoJson(
            { invitation: inv, delivery: smtp ? "email" : "inbox", link: null },
            201,
          );
        }
        return demoJson(
          {
            invitation: inv,
            delivery: smtp ? "email" : "manual",
            link: smtp
              ? null
              : `${window.location.origin}/project-invite/hspi_demo_ok`,
          },
          201,
        );
      }),
    },
    {
      method: "POST",
      pattern: "/projects/:projectId/invitations/:invitationId/resend",
      handler: project("manage", (req, p, state, world) => {
        const inv = listOf(state, p.summary.id).find(
          (i) => i.id === req.params.invitationId,
        );
        if (!inv) return notFound();
        if (inv.status !== "pending" && inv.status !== "expired") {
          return demoError(409, "invitation_not_pending", "Not pending");
        }
        if (inv.sent_count >= 6) {
          return demoError(429, "invitation_resend_too_soon", "Too soon");
        }
        inv.sent_count += 1;
        inv.last_sent_at = now();
        inv.status = "pending";
        inv.expires_at = new Date(Date.now() + 7 * DAY).toISOString();
        const manual =
          inv.invitee.kind === "email" && !world.bootstrap.auth.smtp_enabled;
        return demoJson({
          invitation: inv,
          delivery: manual ? "manual" : "email",
          link: manual
            ? `${window.location.origin}/project-invite/hspi_demo_ok`
            : null,
        });
      }),
    },
    {
      method: "DELETE",
      pattern: "/projects/:projectId/invitations/:invitationId",
      handler: project("manage", (req, p, state) => {
        const inv = listOf(state, p.summary.id).find(
          (i) => i.id === req.params.invitationId,
        );
        if (!inv) return notFound();
        inv.status = "revoked";
        return demoNoContent();
      }),
    },
    {
      method: "GET",
      pattern: "/projects/:projectId/access-requests",
      handler: project("manage", (_req, p, state) =>
        page(
          requestsOf(state, p.summary.id).filter((r) => r.status === "pending"),
        ),
      ),
    },
    {
      method: "POST",
      pattern: "/projects/:projectId/access-requests/:requestId/:decision",
      handler: project("manage", (req, p, state, world) => {
        const r = requestsOf(state, p.summary.id).find(
          (x) => x.id === req.params.requestId,
        );
        if (!r) return notFound();
        if (r.status !== "pending") {
          return demoError(409, "access_request_decided", "Decided");
        }
        const approve = req.params.decision === "approve";
        const role = bodyOf(req).role as GrantRole;
        const user = world.bootstrap.user;
        r.status = approve ? "approved" : "denied";
        r.decided_at = now();
        r.decided_by = user ? { id: user.id, name: user.name } : null;
        r.granted_role = approve ? role : null;
        if (approve) p.roles[r.requester.id] = role;
        for (const n of state.notifications) {
          if (n.payload.ref_id === r.id) n.read_at = now();
        }
        return demoJson(r);
      }),
    },
    {
      method: "GET",
      pattern: "/projects/:projectId/transfer",
      handler: project("view", (_req, p, state, world) => {
        const t = state.transfers[p.summary.id];
        if (!t) return demoJson({ pending: false, transfer: null });
        const owner =
          effectiveRole(world, p, world.bootstrap.user?.id) === "owner";
        return demoJson({
          pending: true,
          transfer: owner
            ? {
                id: `trf_${p.summary.id}`,
                to: t.to,
                created_at: t.created_at,
                expires_at: t.expires_at,
                message: t.message,
              }
            : null,
        });
      }),
    },
    {
      method: "GET",
      pattern: "/projects/:projectId/transfer-candidates",
      handler: project("manage", (req, _p, _state, world) => {
        const q =
          typeof req.query.q === "string" ? req.query.q.toLowerCase() : "";
        const me = world.bootstrap.user?.id;
        const people = adminOrgsOf(world)
          .directory.filter((u) => u.id !== me)
          .map((u) => ({
            kind: "user",
            id: u.id,
            name: u.name,
            detail: u.email,
          }));
        const orgs = (world.bootstrap.user?.org_roles ?? [])
          .filter((o) => o.role !== "member")
          .map((o) => ({
            kind: "org",
            id: o.slug,
            name: o.name,
            detail: o.slug,
          }));
        const items = [...orgs, ...people].filter(
          (c) => q === "" || `${c.name} ${c.detail}`.toLowerCase().includes(q),
        );
        return demoJson({
          items: items.slice(0, 20),
          has_more: items.length > 20,
        });
      }),
    },
    {
      method: "POST",
      pattern: "/projects/:projectId/transfer",
      handler: project("manage", (req, p, state, world) => {
        const body = bodyOf(req);
        const kind = body.to_kind === "org" ? "org" : "user";
        const id = str(body.to_id) ?? "";
        if (kind === "org") {
          if (body.confirm_name !== p.summary.name) {
            return demoError(422, "confirm_name_mismatch", "Name mismatch");
          }
          const org = world.bootstrap.user?.org_roles.find(
            (o) => o.slug === id,
          );
          if (!org) return notFound();
          p.summary.owner = { kind: "org", id, name: org.name, slug: id };
          state.transfers[p.summary.id] = undefined;
          return demoJson({ pending: false, transfer: null }, 201);
        }
        const person = adminOrgsOf(world).directory.find((u) => u.id === id);
        if (!person) return notFound();
        const t = {
          projectId: p.summary.id,
          to: { kind: "user" as const, id, name: person.name },
          created_at: now(),
          expires_at: new Date(Date.now() + 7 * DAY).toISOString(),
          message: str(body.message),
        };
        state.transfers[p.summary.id] = t;
        return demoJson(
          {
            pending: true,
            transfer: {
              id: `trf_${p.summary.id}`,
              to: t.to,
              created_at: t.created_at,
              expires_at: t.expires_at,
              message: t.message,
            },
          },
          201,
        );
      }),
    },
    {
      method: "DELETE",
      pattern: "/projects/:projectId/transfer",
      handler: project("manage", (_req, p, state) => {
        if (!state.transfers[p.summary.id]) return notFound();
        state.transfers[p.summary.id] = undefined;
        return demoNoContent();
      }),
    },
    // Адресат
    {
      method: "GET",
      pattern: "/account/invitations",
      handler: signedIn((_req, _w, state) =>
        demoJson({
          items: state.myInvitations.filter(
            (i) => i.status === "pending" || i.status === "expired",
          ),
        }),
      ),
    },
    {
      method: "POST",
      pattern: "/account/invitations/:invitationId/:decision",
      handler: signedIn((req, world, state, userId) => {
        const inv = state.myInvitations.find(
          (i) => i.id === req.params.invitationId,
        );
        if (!inv) return notFound();
        if (inv.status === "expired") {
          return demoError(410, "invitation_expired", "Expired");
        }
        if (inv.status !== "pending") {
          return demoError(409, "invitation_not_pending", "Not pending");
        }
        const accept = req.params.decision === "accept";
        inv.status = accept ? "accepted" : "declined";
        const p = world.projects.find((x) => x.summary.id === inv.project.id);
        if (accept && p) p.roles[userId] = inv.role;
        return demoJson(inv);
      }),
    },
    {
      method: "GET",
      pattern: "/project-invitations/:token",
      handler: (req) => {
        const preview = invitesOf(getWorld()).previews[req.params.token ?? ""];
        return demoJson(
          preview ?? {
            state: "invalid",
            project_name: null,
            inviter_name: null,
            role: null,
            email_hint: null,
            registration_token: null,
          },
        );
      },
    },
    {
      method: "POST",
      pattern: "/project-invitations/:token/accept",
      handler: signedIn((req, _w, state) => {
        const token = req.params.token ?? "";
        if (token === "hspi_demo_mismatch") {
          return demoError(403, "invitation_email_mismatch", "Mismatch", {
            email_hint: "p***@hse.ru",
          });
        }
        const preview = state.previews[token];
        if (preview?.state !== "ok") return notFound();
        preview.state = "used";
        const mine = state.myInvitations[0];
        return mine ? demoJson({ ...mine, status: "accepted" }) : notFound();
      }),
    },
    {
      method: "GET",
      pattern: "/account/transfers",
      handler: signedIn((_req, _w, state) =>
        demoJson({
          items: state.myTransfers.filter((t) => t.status === "pending"),
        }),
      ),
    },
    {
      method: "POST",
      pattern: "/account/transfers/:transferId/:decision",
      handler: signedIn((req, world, state, userId) => {
        const t = state.myTransfers.find((x) => x.id === req.params.transferId);
        if (t?.status !== "pending") return notFound();
        const accept = req.params.decision === "accept";
        t.status = accept ? "accepted" : "declined";
        const p = world.projects.find((x) => x.summary.id === t.project.id);
        if (accept && p) {
          const user = world.bootstrap.user;
          const previous = p.summary.owner;
          p.summary.owner = {
            kind: "user",
            id: userId,
            name: user?.name ?? "",
            slug: null,
          };
          p.roles[userId] = "owner";
          if (previous.kind === "user") p.roles[previous.id] = "editor";
        }
        return demoJson(t);
      }),
    },
    {
      method: "GET",
      pattern: "/account/access-requests",
      handler: signedIn((_req, _w, state) =>
        demoJson({ items: state.myRequests }),
      ),
    },
    {
      method: "DELETE",
      pattern: "/account/access-requests/:requestId",
      handler: signedIn((req, _w, state) => {
        const r = state.myRequests.find((x) => x.id === req.params.requestId);
        if (!r) return notFound();
        r.status = "cancelled";
        return demoNoContent();
      }),
    },
    {
      method: "POST",
      pattern: "/access-requests",
      handler: signedIn((req, _w, state) => {
        const projectId = str(bodyOf(req).project_id);
        if (
          projectId &&
          !state.myRequests.some(
            (r) => r.project.id === projectId && r.status === "pending",
          )
        ) {
          state.myRequests.unshift({
            id: nextId(state, "arq"),
            project: { id: projectId, name: null },
            status: "pending",
            created_at: now(),
            decided_at: null,
            granted_role: null,
          });
        }
        return demoJson({ accepted: true }, 202);
      }),
    },
    // «Входящие»
    {
      method: "GET",
      pattern: "/account/notifications",
      handler: signedIn((_req, _w, state) => page(state.notifications)),
    },
    {
      method: "POST",
      pattern: "/account/notifications/read",
      handler: signedIn((req, _w, state) => {
        const ids = bodyOf(req).ids;
        for (const n of state.notifications) {
          if (
            n.read_at === null &&
            (!Array.isArray(ids) || ids.includes(n.id))
          ) {
            n.read_at = now();
          }
        }
        return demoNoContent();
      }),
    },
    {
      method: "GET",
      pattern: "/account/inbox/summary",
      handler: signedIn((_req, world, state, userId) => {
        const managed = Object.entries(state.projectRequests).filter(([id]) => {
          const p = world.projects.find((x) => x.summary.id === id);
          return p !== undefined && effectiveRole(world, p, userId) === "owner";
        });
        return demoJson({
          unread: state.notifications.filter((n) => n.read_at === null).length,
          invitations: state.myInvitations.filter((i) => i.status === "pending")
            .length,
          transfers: state.myTransfers.filter((t) => t.status === "pending")
            .length,
          access_requests: managed
            .flatMap(([, list]) => list)
            .filter((r) => r.status === "pending").length,
        });
      }),
    },
  ];
};
