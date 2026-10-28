import { demoError, demoJson } from "@shared/api/demo";
import type { DemoRoute } from "@shared/api/demo";
import type { ProjectRole } from "@entities/session";
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
  project: DemoProject,
  userId: string | undefined,
): ProjectRole | null =>
  userId === undefined ? null : (project.roles[userId] ?? null);

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

export const createProjectRoutes = (
  getWorld: () => ServerDemoWorld,
): DemoRoute[] => [
  {
    method: "GET",
    pattern: "/projects",
    handler: () => {
      const world = getWorld();
      const user = world.bootstrap.user;
      if (!user) {
        return demoError(401, "auth_required", "Authentication required");
      }
      const items = world.projects.flatMap((project) => {
        const role = roleOf(project, user.id);
        return role ? [{ ...project.summary, my_role: role }] : [];
      });
      return demoJson(items);
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
    method: "GET",
    pattern: "/projects/:projectId",
    handler: (req) => {
      const world = getWorld();
      const project = world.projects.find(
        (p) => p.summary.id === req.params.projectId,
      );
      const role = project ? roleOf(project, world.bootstrap.user?.id) : null;
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
      const role = project ? roleOf(project, world.bootstrap.user?.id) : null;
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
