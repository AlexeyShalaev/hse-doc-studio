import { demoError, demoJson, demoNoContent } from "@shared/api/demo";
import type { DemoResponse, DemoRoute } from "@shared/api/demo";
import type {
  AdminSharingSettings,
  LinkRole,
  OrgSharingPolicy,
  ShareLink,
  ShareLinkPreview,
  ShareLinkVisit,
} from "@entities/share-link";
import { createProjectRoutes } from "./projectRoutes";
import { effectiveRole } from "./projectAccess";
import { DEMO_STUDENT } from "./scenarios";
import type { ServerDemoWorld } from "./world";

// Демо ссылок доступа (трек links): ссылки проекта у Анны, страница ссылки,
// гостевая сессия, просмотр PDF гостем, политика организации и установки.
// Правила те же, что у настоящего API (раздел 8.1 спецификации). Особые токены
// страницы /s/:token, чтобы вызвать каждое состояние руками:
//  - hsl_demoReader: Читатель без исходников (ведёт на просмотр PDF);
//  - hsl_demoEditor: Редактор, нужно имя гостя;
//  - hsl_demoPassword: пароль «password1», затем имя (Редактор);
//  - hsl_demoLogin: нужен вход; hsl_demoOrg: только участникам организации;
//  - любой другой токен: ссылка не действует.
// Подпись ссылки, начинающаяся с limit, отвечает 409 link_limit.

const BERTIE = "p_01hxa1c4de";
const QUEUE = "p_01hxa3k2jm";
const ORIGIN = "https://studio.example.org";
const GUEST_CSRF = "Gq8vT1mZ3xK0cR7bN5yH2wLsJp9eDg6o";
const ROLE_ORDER: readonly LinkRole[] = ["reader", "reviewer", "editor"];

type DemoLink = ShareLink & {
  project_id: string;
  token: string;
  password: string | null;
};

type DemoSharing = {
  links: DemoLink[];
  visits: Record<string, ShareLinkVisit[]>;
  orgPolicies: Record<string, OrgSharingPolicy>;
  admin: AdminSharingSettings;
  seq: number;
};

const states = new WeakMap<ServerDemoWorld, DemoSharing>();

const anna = { id: DEMO_STUDENT.id, name: DEMO_STUDENT.name };

const seedLink = (
  id: string,
  token: string,
  extra: Partial<DemoLink>,
): DemoLink => ({
  id,
  project_id: BERTIE,
  token,
  password: null,
  label: "Для научрука",
  role: "reader",
  show_sources: false,
  require_login: false,
  has_password: false,
  url: `${ORIGIN}/s/${token}`,
  token_prefix: token.slice(4, 12),
  created_by: anna,
  created_at: "2026-10-28T09:00:00Z",
  updated_at: "2026-10-28T09:00:00Z",
  expires_at: "2026-12-31T00:00:00Z",
  state: "active",
  blocked_reason: null,
  editable: true,
  visits: { visitors: 0, opens: 0, last_at: null },
  ...extra,
});

const seed = (): DemoSharing => ({
  links: [
    seedLink("lnk_demo_reader", "hsl_demoReader", {
      visits: { visitors: 2, opens: 4, last_at: "2026-10-31T14:02:00Z" },
    }),
    seedLink("lnk_demo_editor", "hsl_demoEditor", {
      label: "Для группы",
      role: "editor",
      show_sources: true,
      expires_at: null,
      created_at: "2026-10-29T10:00:00Z",
    }),
    seedLink("lnk_demo_password", "hsl_demoPassword", {
      label: "Защищённая",
      role: "editor",
      show_sources: true,
      has_password: true,
      password: "password1",
      created_at: "2026-10-29T11:00:00Z",
    }),
    seedLink("lnk_demo_login", "hsl_demoLogin", {
      label: "Для кафедры",
      role: "reviewer",
      show_sources: true,
      require_login: true,
      created_at: "2026-10-29T12:00:00Z",
    }),
    seedLink("lnk_demo_old", "hsl_demoOld", {
      label: "Старая ссылка",
      state: "revoked",
      url: null,
      editable: false,
      created_at: "2026-10-20T12:00:00Z",
    }),
    seedLink("lnk_demo_queue", "hsl_demoQueue", {
      project_id: QUEUE,
      label: "Для научрука",
      created_by: { id: "u_01hx7k5pavel", name: "Павел Орлов" },
    }),
  ],
  visits: {
    lnk_demo_reader: [
      {
        visitor_kind: "guest",
        name: "Пётр Иванович",
        first_at: "2026-10-30T13:50:00Z",
        last_at: "2026-10-31T14:02:00Z",
        opens: 3,
      },
      {
        visitor_kind: "user",
        name: "Иван Сидоров",
        first_at: "2026-10-30T09:00:00Z",
        last_at: "2026-10-30T09:00:00Z",
        opens: 1,
      },
    ],
  },
  orgPolicies: {},
  admin: {
    links_enabled: true,
    max_link_role: "editor",
    project_invites_allow_signup: true,
    fields: {
      "sharing.links_enabled": { source: "default", locked: false },
      "sharing.max_link_role": { source: "default", locked: false },
      "registration.project_invites_allow_signup": {
        source: "default",
        locked: false,
      },
    },
  },
  seq: 1,
});

export const sharingOf = (world: ServerDemoWorld): DemoSharing => {
  let state = states.get(world);
  if (!state) {
    state = seed();
    states.set(world, state);
  }
  return state;
};

const notFound = () => demoError(404, "not_found", "Not found or no access");
const publicView = ({
  project_id: _p,
  token: _t,
  password: _w,
  ...link
}: DemoLink): ShareLink => link;

const projectRole = (world: ServerDemoWorld, projectId: string) => {
  const project = world.projects.find((p) => p.summary.id === projectId);
  const role = project
    ? effectiveRole(world, project, world.bootstrap.user?.id)
    : null;
  return { project, role };
};

const listFor = (
  world: ServerDemoWorld,
  projectId: string,
  includeRevoked: boolean,
): DemoResponse => {
  const { role } = projectRole(world, projectId);
  if (!role) return notFound();
  if (role !== "owner" && role !== "editor")
    return demoError(403, "forbidden_role", "Forbidden", {
      required_role: "editor",
    });
  const sharing = sharingOf(world);
  const userId = world.bootstrap.user?.id;
  const own = sharing.links.filter(
    (l) =>
      l.project_id === projectId &&
      (role === "owner" || l.created_by?.id === userId),
  );
  const items = own
    .filter((l) => includeRevoked || l.state !== "revoked")
    .map((l) => ({
      ...publicView(l),
      created_by: role === "owner" ? l.created_by : null,
    }));
  return demoJson({
    items,
    can_create: sharing.admin.links_enabled,
    max_role:
      role === "owner" || role === "editor"
        ? sharing.admin.max_link_role
        : "reader",
    forced_login: false,
    revoked_count: own.filter((l) => l.state === "revoked").length,
  });
};

const body = (req: { body: unknown }): Record<string, unknown> =>
  (req.body ?? {}) as Record<string, unknown>;
const daysFromNow = (days: unknown): string | null =>
  typeof days === "number"
    ? new Date(Date.now() + days * 86_400_000).toISOString()
    : null;

const guestEnter = (
  world: ServerDemoWorld,
  link: DemoLink,
  name: string | null,
): void => {
  const current = world.bootstrap.guest ?? { name: null, links: [] };
  const project = world.projects.find((p) => p.summary.id === link.project_id);
  world.bootstrap = {
    ...world.bootstrap,
    user: null,
    csrf_token: GUEST_CSRF,
    capabilities: Object.fromEntries(
      Object.keys(world.bootstrap.capabilities).map((k) => [k, false]),
    ) as typeof world.bootstrap.capabilities,
    guest: {
      name: name ?? current.name,
      links: [
        {
          project_id: link.project_id,
          project_name: project?.summary.name ?? "",
          link_label: link.label,
          role: link.role,
          show_sources: link.show_sources,
        },
        ...current.links.filter((l) => l.project_id !== link.project_id),
      ],
    },
  };
};

const guestLinkOf = (world: ServerDemoWorld, projectId: string) =>
  world.bootstrap.user === null
    ? world.bootstrap.guest?.links.find((l) => l.project_id === projectId)
    : undefined;

const preview = (world: ServerDemoWorld, token: string): ShareLinkPreview => {
  const signedIn = world.bootstrap.user !== null;
  const hidden: ShareLinkPreview = {
    state: "inactive",
    project_name: null,
    owner_name: null,
    role: null,
    show_sources: false,
    guest_name_required: false,
    signed_in: signedIn,
  };
  if (token === "hsl_demoOrg") {
    return {
      ...hidden,
      state: "org_only",
      project_name: "Industry adoption of CI",
      owner_name: "МСПИН 2025",
      role: "reviewer",
      show_sources: true,
    };
  }
  const link = sharingOf(world).links.find(
    (l) => l.token === token && l.state === "active",
  );
  if (!link) return hidden;
  if (link.has_password) return { ...hidden, state: "password_required" };
  const project = world.projects.find((p) => p.summary.id === link.project_id);
  const details = {
    project_name: project?.summary.name ?? "",
    owner_name: project?.summary.owner.name ?? "",
    role: link.role,
    show_sources: link.show_sources,
    signed_in: signedIn,
  };
  if (link.require_login && !signedIn)
    return { ...details, state: "login_required", guest_name_required: false };
  return {
    ...details,
    state: "ok",
    guest_name_required: !signedIn && link.role !== "reader",
  };
};

const DOCS = [
  {
    id: "vkr",
    def_id: "vkr",
    name: { ru: "Пояснительная записка", en: "Explanatory note" },
    status: "ok" as const,
    last_compile_id: "c_demo_vkr",
    pages: 64,
  },
  {
    id: "tz",
    def_id: "tz",
    name: { ru: "Техническое задание", en: "Requirements specification" },
    status: "draft" as const,
    last_compile_id: null,
    pages: null,
  },
];

export const createShareLinkRoutes = (
  getWorld: () => ServerDemoWorld,
): DemoRoute[] => {
  const projectDetail = createProjectRoutes(getWorld).find(
    (r) => r.method === "GET" && r.pattern === "/projects/:projectId",
  );
  return [
    {
      method: "GET",
      pattern: "/projects/:projectId/links",
      handler: (req) =>
        listFor(
          getWorld(),
          req.params.projectId ?? "",
          req.query.include_revoked === "true",
        ),
    },
    {
      method: "POST",
      pattern: "/projects/:projectId/links",
      handler: (req) => {
        const world = getWorld();
        const projectId = req.params.projectId ?? "";
        const { role } = projectRole(world, projectId);
        if (!role) return notFound();
        const b = body(req);
        const label = typeof b.label === "string" ? b.label.trim() : "";
        if (label.startsWith("limit"))
          return demoError(409, "link_limit", "Link limit");
        const wanted = (b.role as LinkRole | undefined) ?? "reader";
        const sharing = sharingOf(world);
        if (
          ROLE_ORDER.indexOf(wanted) >
          ROLE_ORDER.indexOf(sharing.admin.max_link_role)
        ) {
          return demoError(422, "link_role_too_high", "Role too high");
        }
        const password =
          typeof b.password === "string" && b.password !== ""
            ? b.password
            : null;
        if (password !== null && password.length < 8)
          return demoError(422, "link_password_invalid", "Password");
        const token = `hsl_demoNew${String(sharing.seq++)}x${Math.random().toString(36).slice(2, 10)}`;
        const now = new Date().toISOString();
        const link = seedLink(`lnk_demo_${token.slice(4)}`, token, {
          project_id: projectId,
          label,
          role: wanted,
          show_sources: wanted !== "reader" || b.show_sources === true,
          require_login: b.require_login === true,
          has_password: password !== null,
          password,
          created_at: now,
          updated_at: now,
          expires_at: daysFromNow(b.expires_in_days),
          created_by: {
            id: world.bootstrap.user?.id ?? "",
            name: world.bootstrap.user?.name ?? "",
          },
        });
        sharing.links.unshift(link);
        return demoJson(publicView(link), 201);
      },
    },
    {
      method: "PATCH",
      pattern: "/projects/:projectId/links/:linkId",
      handler: (req) => {
        const world = getWorld();
        const link = sharingOf(world).links.find(
          (l) => l.id === req.params.linkId,
        );
        if (!link || !projectRole(world, link.project_id).role)
          return notFound();
        if (link.state === "revoked")
          return demoError(409, "link_revoked", "Revoked");
        const b = body(req);
        if (typeof b.label === "string") link.label = b.label;
        if (typeof b.role === "string") link.role = b.role as LinkRole;
        if (typeof b.show_sources === "boolean")
          link.show_sources = b.show_sources;
        if (link.role !== "reader") link.show_sources = true;
        if (typeof b.require_login === "boolean")
          link.require_login = b.require_login;
        if (typeof b.password === "string" && b.password !== "") {
          link.password = b.password;
          link.has_password = true;
        }
        if (b.clear_password === true) {
          link.password = null;
          link.has_password = false;
        }
        if (typeof b.expires_in_days === "number") {
          link.expires_at = daysFromNow(b.expires_in_days);
          link.state = "active";
          link.url = `${ORIGIN}/s/${link.token}`;
        }
        if (b.clear_expiry === true) link.expires_at = null;
        link.updated_at = new Date().toISOString();
        return demoJson(publicView(link));
      },
    },
    {
      method: "POST",
      pattern: "/projects/:projectId/links/:linkId/rotate",
      handler: (req) => {
        const world = getWorld();
        const sharing = sharingOf(world);
        const old = sharing.links.find((l) => l.id === req.params.linkId);
        if (!old || !projectRole(world, old.project_id).role) return notFound();
        if (old.state === "revoked")
          return demoError(409, "link_revoked", "Revoked");
        const token = `hsl_demoRot${String(sharing.seq++)}x${Math.random().toString(36).slice(2, 10)}`;
        const fresh: DemoLink = {
          ...old,
          id: `lnk_demo_${token.slice(4)}`,
          token,
          url: `${ORIGIN}/s/${token}`,
          token_prefix: token.slice(4, 12),
          visits: { visitors: 0, opens: 0, last_at: null },
        };
        Object.assign(old, { state: "revoked", url: null, editable: false });
        sharing.links.unshift(fresh);
        return demoJson(publicView(fresh));
      },
    },
    {
      method: "DELETE",
      pattern: "/projects/:projectId/links/:linkId",
      handler: (req) => {
        const world = getWorld();
        const link = sharingOf(world).links.find(
          (l) => l.id === req.params.linkId,
        );
        if (!link || !projectRole(world, link.project_id).role)
          return notFound();
        Object.assign(link, { state: "revoked", url: null, editable: false });
        return demoNoContent();
      },
    },
    {
      method: "GET",
      pattern: "/projects/:projectId/links/:linkId/visits",
      handler: (req) => {
        const items =
          sharingOf(getWorld()).visits[req.params.linkId ?? ""] ?? [];
        return demoJson({ items, total: items.length, limit: 50, offset: 0 });
      },
    },
    {
      method: "GET",
      pattern: "/links/:token",
      handler: (req) => demoJson(preview(getWorld(), req.params.token ?? "")),
    },
    {
      method: "POST",
      pattern: "/links/:token/open",
      handler: (req) => {
        const world = getWorld();
        const token = req.params.token ?? "";
        const link = sharingOf(world).links.find(
          (l) => l.token === token && l.state === "active",
        );
        if (!link) return demoError(404, "link_inactive", "Link inactive");
        const b = body(req);
        if (link.password !== null && b.password !== link.password) {
          return demoError(403, "link_password_wrong", "Wrong password");
        }
        const signedIn = world.bootstrap.user !== null;
        const name =
          typeof b.guest_name === "string" ? b.guest_name.trim() : "";
        if (!signedIn && link.require_login)
          return demoError(401, "link_login_required", "Sign in");
        if (!signedIn && link.role !== "reader" && name === "") {
          return demoError(422, "guest_name_required", "Name required");
        }
        if (!signedIn) guestEnter(world, link, name || null);
        return demoJson({
          project_id: link.project_id,
          mode: signedIn ? "user" : "guest",
          role: link.role,
          show_sources: link.show_sources,
          landing:
            link.role === "reader" && !link.show_sources ? "view" : "workspace",
        });
      },
    },
    {
      method: "PATCH",
      pattern: "/links/session",
      handler: (req) => {
        const world = getWorld();
        const guest = world.bootstrap.guest;
        if (!guest) return demoError(401, "auth_required", "Sign in required");
        const name = (
          typeof body(req).name === "string" ? (body(req).name as string) : ""
        ).trim();
        if (!name)
          return demoError(422, "guest_name_required", "Name required");
        world.bootstrap = { ...world.bootstrap, guest: { ...guest, name } };
        return demoJson(world.bootstrap.guest);
      },
    },
    {
      method: "DELETE",
      pattern: "/links/session",
      handler: () => {
        const world = getWorld();
        world.bootstrap = { ...world.bootstrap, guest: null, csrf_token: null };
        return demoNoContent();
      },
    },
    // Гость в проекте: карточка проекта и документы по ссылке; остальное как у вошедшего.
    {
      method: "GET",
      pattern: "/projects/:projectId",
      handler: async (req) => {
        const world = getWorld();
        const link = guestLinkOf(world, req.params.projectId ?? "");
        const project = world.projects.find(
          (p) => p.summary.id === req.params.projectId,
        );
        if (world.bootstrap.guest && world.bootstrap.user === null) {
          if (!link || !project)
            return demoError(404, "link_inactive", "Link inactive");
          return demoJson({
            id: project.summary.id,
            name: project.summary.name,
            folder: "",
            lock: {
              pack_id: "hse-cs-sse",
              template_id: "course-project",
              version: "1.0.0",
              engine: "xelatex",
            },
            kind: project.summary.kind,
            staffing: project.summary.staffing,
            lang: project.summary.lang,
            updated_at: project.summary.updated_at,
            pinned: false,
            archived: false,
            shared_enabled: project.summary.shared_enabled,
            owner: project.summary.owner,
            my_role: link.role,
            via_link: true,
            link_label: link.link_label,
          });
        }
        return projectDetail ? projectDetail.handler(req) : notFound();
      },
    },
    {
      method: "GET",
      pattern: "/projects/:projectId/documents",
      handler: (req) => {
        const world = getWorld();
        const projectId = req.params.projectId ?? "";
        const link = guestLinkOf(world, projectId);
        const { role } = projectRole(world, projectId);
        if (!link && !role) return notFound();
        return demoJson(DOCS);
      },
    },
    {
      method: "GET",
      pattern: "/orgs/:slug/sharing-policy",
      handler: (req) => {
        const world = getWorld();
        const slug = req.params.slug ?? "";
        const membership = world.bootstrap.user?.org_roles.find(
          (o) => o.slug === slug,
        );
        if (!membership) return notFound();
        const stored = sharingOf(world).orgPolicies[slug] ?? {
          links: "any",
          max_link_role: "editor",
          nda_public_links: false,
          external_invites: true,
          editable: false,
        };
        return demoJson({ ...stored, editable: membership.role !== "member" });
      },
    },
    {
      method: "PUT",
      pattern: "/orgs/:slug/sharing-policy",
      handler: (req) => {
        const world = getWorld();
        const slug = req.params.slug ?? "";
        const membership = world.bootstrap.user?.org_roles.find(
          (o) => o.slug === slug,
        );
        if (!membership) return notFound();
        if (membership.role === "member")
          return demoError(403, "forbidden", "Forbidden");
        const next = { ...(body(req) as OrgSharingPolicy), editable: true };
        sharingOf(world).orgPolicies[slug] = next;
        return demoJson(next);
      },
    },
  ];
};

/** `/api/admin/settings/sharing` на adminClient. */
export const createSharingAdminRoutes = (
  getWorld: () => ServerDemoWorld,
): DemoRoute[] => [
  {
    method: "GET",
    pattern: "/settings/sharing",
    handler: () => demoJson(sharingOf(getWorld()).admin),
  },
  {
    method: "PUT",
    pattern: "/settings/sharing",
    handler: (req) => {
      const sharing = sharingOf(getWorld());
      const b = body(req);
      const next = { ...sharing.admin, fields: { ...sharing.admin.fields } };
      if (typeof b.links_enabled === "boolean") {
        next.links_enabled = b.links_enabled;
        next.fields["sharing.links_enabled"] = {
          source: "admin",
          locked: false,
        };
      }
      if (typeof b.max_link_role === "string") {
        next.max_link_role = b.max_link_role as LinkRole;
        next.fields["sharing.max_link_role"] = {
          source: "admin",
          locked: false,
        };
      }
      if (typeof b.project_invites_allow_signup === "boolean") {
        next.project_invites_allow_signup = b.project_invites_allow_signup;
        next.fields["registration.project_invites_allow_signup"] = {
          source: "admin",
          locked: false,
        };
      }
      sharing.admin = next;
      return demoJson(next);
    },
  },
];
