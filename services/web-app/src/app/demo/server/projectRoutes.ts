import { demoError, demoJson } from "@shared/api/demo";
import type { DemoRoute } from "@shared/api/demo";
import type { ProjectRole } from "@entities/session";
import {
  boolParam,
  invalidQuery,
  offsetList,
  queryOne,
  wantsPage,
} from "./demoList";
import { effectiveRole } from "./projectAccess";
import type { DemoProject } from "./projects";
import type { ServerDemoWorld } from "./world";

// Демо проектов сервера: список с владельцем и ролью, создание без папки, карточка
// проекта, закрепление и архив. Особые случаи:
//  - чужой и несуществующий проект отвечают 404 (id p_01hxa9foreign и любой другой);
//  - архивировать может только владелец: остальные получают 403 forbidden_role;
//  - создание с названием forbidden-org отвечает 403 «нужна роль Владелец».

const str = (value: unknown): string =>
  typeof value === "string" ? value : "";

const notFound = () =>
  demoError(404, "not_found", "Project not found or no access");

const roleOf = (
  world: ServerDemoWorld,
  project: DemoProject,
  userId: string | undefined,
): ProjectRole | null => effectiveRole(world, project, userId);

const detail = (project: DemoProject, role: ProjectRole) => ({
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
  pinned: project.summary.pinned,
  archived: project.summary.archived,
  shared_enabled: project.summary.shared_enabled,
  owner: project.summary.owner,
  my_role: role,
});

const IMPORT_REFUSALS: readonly (readonly [string, number, string, string])[] =
  [
    [
      "evil",
      422,
      "import_archive_unsafe",
      "The archive was rejected: unsafe path or file type",
    ],
    ["huge", 413, "import_too_large", "The project is too large"],
    ["empty", 422, "import_no_project", "The archive holds no Studio project"],
    [
      "newer",
      422,
      "import_project_newer",
      "The project was saved by a newer Studio",
    ],
    [
      "broken",
      422,
      "import_archive_invalid",
      "This is not a zip archive or it is damaged",
    ],
  ];

export const createProjectRoutes = (
  getWorld: () => ServerDemoWorld,
): DemoRoute[] => [
  {
    method: "GET",
    pattern: "/projects",
    handler: (req) => {
      const world = getWorld();
      const user = world.bootstrap.user;
      if (!user) {
        return demoError(401, "auth_required", "Authentication required");
      }
      const items = world.projects.flatMap((project) => {
        const role = roleOf(world, project, user.id);
        return role ? [{ ...project.summary, my_role: role }] : [];
      });
      // Новый клиент (с limit) получает страницу по контракту; прежний массив.
      if (!wantsPage(req)) return demoJson(items);
      type Row = (typeof items)[number];
      const archived = boolParam(req, "archived");
      const pinned = boolParam(req, "pinned");
      const owner = queryOne(req, "owner");
      const org = queryOne(req, "org");
      if (
        archived === "bad" ||
        pinned === "bad" ||
        (owner !== null && !["me", "org", "shared"].includes(owner))
      ) {
        return invalidQuery();
      }
      const rows = items.filter(
        (p) =>
          (archived === null || p.archived === archived) &&
          (pinned === null || p.pinned === pinned) &&
          (org === null || p.owner.slug === org) &&
          (owner === null ||
            (owner === "me"
              ? p.owner.kind === "user" && p.owner.id === user.id
              : owner === "org"
                ? p.owner.kind === "org"
                : p.my_role !== "owner")),
      );
      return offsetList(req, rows, {
        sort: {
          name: (p: Row) => p.name,
          updated_at: (p: Row) => p.updated_at,
          created_at: (p: Row) => p.updated_at,
        },
        defaultSort: "-updated_at",
        search: (p) => [p.name, p.owner.name],
        id: (p) => p.id,
      });
    },
  },
  {
    method: "POST",
    pattern: "/projects",
    handler: (req) => {
      const world = getWorld();
      const user = world.bootstrap.user;
      if (!user) {
        return demoError(401, "auth_required", "Authentication required");
      }
      const body = (req.body ?? {}) as Record<string, unknown>;
      if ("folder" in body) {
        return demoError(
          422,
          "folder_not_allowed",
          "The server picks the project folder",
        );
      }
      const name = str(body.name).trim();
      if (name === "") {
        return demoError(422, "name_required", "Project name is required");
      }
      if (name.toLowerCase().includes("forbidden-org")) {
        return demoError(403, "forbidden_role", "Forbidden", {
          required_role: "owner",
        });
      }
      const slug =
        typeof body.owner_org_slug === "string" ? body.owner_org_slug : null;
      const org = slug
        ? user.org_roles.find((o) => o.slug === slug)
        : undefined;
      const project: DemoProject = {
        summary: {
          id: `p_demo${String(world.projects.length + 1).padStart(4, "0")}`,
          name,
          kind: body.kind === "research" ? "research" : "project",
          staffing: body.staffing === "team" ? "team" : "solo",
          lang: body.lang === "en" ? "en" : "ru",
          owner: org
            ? {
                kind: "org",
                id: `org_${org.slug}`,
                name: org.name,
                slug: org.slug,
              }
            : { kind: "user", id: user.id, name: user.name, slug: null },
          updated_at: new Date().toISOString(),
          pinned: false,
          archived: false,
          shared_enabled: body.shared_enabled !== false,
        },
        roles: { [user.id]: "owner" },
      };
      world.projects.push(project);
      return demoJson(detail(project, "owner"), 201);
    },
  },
  {
    // Загрузка zip из локальной Студии. Исход выбирает имя файла:
    // evil, huge, empty, newer, broken дают отказы; again даёт новый id; remote даёт предупреждения.
    method: "POST",
    pattern: "/projects/import",
    handler: (req) => {
      const world = getWorld();
      const user = world.bootstrap.user;
      if (!user) {
        return demoError(401, "auth_required", "Authentication required");
      }
      const file = req.body instanceof FormData ? req.body.get("file") : null;
      const name = file instanceof File ? file.name.toLowerCase() : "";
      const refusal = IMPORT_REFUSALS.find(([word]) => name.includes(word));
      if (refusal) {
        const [, status, code, text] = refusal;
        return demoError(status, code, text);
      }
      const project: DemoProject = {
        summary: {
          id: `p_demo${String(world.projects.length + 1).padStart(4, "0")}`,
          name: "Курсовая из локальной Студии",
          kind: "research",
          staffing: "solo",
          lang: "ru",
          owner: { kind: "user", id: user.id, name: user.name, slug: null },
          updated_at: new Date().toISOString(),
          pinned: false,
          archived: false,
          shared_enabled: true,
        },
        roles: { [user.id]: "owner" },
      };
      world.projects.push(project);
      const remote = name.includes("remote");
      return demoJson(
        {
          project_id: project.summary.id,
          name: project.summary.name,
          id_regenerated: name.includes("again"),
          files: 42,
          bytes: 3_145_728,
          chats: remote ? 0 : 2,
          warnings: remote
            ? [
                { code: "remote_needs_access", detail: "" },
                { code: "records_skipped", detail: "6" },
              ]
            : [],
        },
        201,
      );
    },
  },
  {
    method: "GET",
    pattern: "/projects/:projectId",
    handler: (req) => {
      const world = getWorld();
      const project = world.projects.find(
        (p) => p.summary.id === req.params.projectId,
      );
      const role = project
        ? roleOf(world, project, world.bootstrap.user?.id)
        : null;
      return project && role ? demoJson(detail(project, role)) : notFound();
    },
  },
  {
    method: "PATCH",
    pattern: "/projects/:projectId",
    handler: (req) => {
      const world = getWorld();
      const project = world.projects.find(
        (p) => p.summary.id === req.params.projectId,
      );
      const role = project
        ? roleOf(world, project, world.bootstrap.user?.id)
        : null;
      if (!project || !role) return notFound();
      const body = (req.body ?? {}) as Record<string, unknown>;
      if (typeof body.archived === "boolean" && role !== "owner") {
        return demoError(403, "forbidden_role", "Forbidden", {
          required_role: "owner",
        });
      }
      if (typeof body.pinned === "boolean")
        project.summary.pinned = body.pinned;
      if (typeof body.archived === "boolean") {
        project.summary.archived = body.archived;
      }
      if (typeof body.name === "string") project.summary.name = body.name;
      return demoJson(detail(project, role));
    },
  },
];
