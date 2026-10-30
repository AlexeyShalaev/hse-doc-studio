import { demoError, demoJson, demoNoContent } from "@shared/api/demo";
import type { DemoResponse, DemoRoute } from "@shared/api/demo";
import type { ProjectRole } from "@entities/session";
import {
  accessCandidates,
  accessEntries,
  effectiveRole,
  findGroup,
} from "./projectAccess";
import type { DemoProject } from "./projects";
import { adminOrgsOf, type ServerDemoWorld } from "./world";

// Демо панели «Доступ» проекта. Правила настоящего API:
//  - список видит любой, у кого есть роль; чужой и несуществующий проект это 404;
//  - менять и искать кандидатов может только владелец: иначе 403 forbidden_role (нужна роль Владелец);
//  - владельца проекта и доступ через организацию здесь не меняют (409 last_owner);
//  - роль Владелец через панель не выдаётся (передача проекта это отдельная операция): 422 input_invalid;
//  - неизвестный человек или группа дают 404 member_not_found.

const ROLES: readonly ProjectRole[] = ["reader", "reviewer", "editor", "owner"];

const str = (value: unknown): string =>
  typeof value === "string" ? value : "";

const notFound = () => demoError(404, "not_found", "Not Found");
const unknownSubject = () =>
  demoError(404, "member_not_found", "Subject not found");
const lastOwner = () => demoError(409, "last_owner", "Cannot change the owner");

export const createProjectAccessRoutes = (
  getWorld: () => ServerDemoWorld,
): DemoRoute[] => {
  const withProject =
    (
      needOwner: boolean,
      handler: (
        project: DemoProject,
        req: Parameters<DemoRoute["handler"]>[0],
        world: ServerDemoWorld,
      ) => DemoResponse,
    ): DemoRoute["handler"] =>
    (req) => {
      const world = getWorld();
      const user = world.bootstrap.user;
      if (!user) {
        return demoError(401, "auth_required", "Authentication required");
      }
      const project = world.projects.find(
        (p) => p.summary.id === req.params.projectId,
      );
      const role = project ? effectiveRole(world, project, user.id) : null;
      if (!project || !role) return notFound();
      if (needOwner && role !== "owner") {
        return demoError(403, "forbidden_role", "Forbidden", {
          required_role: "owner",
        });
      }
      return handler(project, req, world);
    };

  return [
    {
      method: "GET",
      pattern: "/projects/:projectId/members",
      handler: withProject(false, (project, _req, world) =>
        demoJson(accessEntries(world, project)),
      ),
    },
    {
      method: "GET",
      pattern: "/projects/:projectId/members/candidates",
      handler: withProject(true, (project, req, world) => {
        const q = req.query.q;
        return demoJson(
          accessCandidates(world, project, typeof q === "string" ? q : ""),
        );
      }),
    },
    {
      method: "PUT",
      pattern: "/projects/:projectId/members",
      handler: withProject(true, (project, req, world) => {
        const body = (req.body ?? {}) as Record<string, unknown>;
        const kind = str(body.subject_kind);
        const id = str(body.subject_id);
        const role = body.role as ProjectRole;
        if (
          (kind !== "user" && kind !== "group") ||
          !ROLES.includes(role) ||
          role === "owner"
        ) {
          return demoError(422, "input_invalid", "Invalid input");
        }
        if (kind === "user") {
          const known = adminOrgsOf(world).directory.some((u) => u.id === id);
          if (!known) return unknownSubject();
          const owner = project.summary.owner;
          if (
            (owner.kind === "user" && owner.id === id) ||
            project.roles[id] === "owner"
          ) {
            return lastOwner();
          }
          project.roles[id] = role;
        } else {
          if (!findGroup(world, id)) return unknownSubject();
          project.groupRoles = { ...project.groupRoles, [id]: role };
        }
        const entry = accessEntries(world, project).find(
          (e) => e.subject_kind === kind && e.subject_id === id,
        );
        return entry ? demoJson(entry) : unknownSubject();
      }),
    },
    {
      method: "DELETE",
      pattern: "/projects/:projectId/members/:kind/:subjectId",
      handler: withProject(true, (project, req) => {
        const kind = req.params.kind;
        const subjectId = req.params.subjectId ?? "";
        if (kind === "user") {
          const owner = project.summary.owner;
          if (
            (owner.kind === "user" && owner.id === subjectId) ||
            project.roles[subjectId] === "owner"
          ) {
            return lastOwner();
          }
          if (!(subjectId in project.roles)) return unknownSubject();
          project.roles = Object.fromEntries(
            Object.entries(project.roles).filter(([id]) => id !== subjectId),
          );
          return demoNoContent();
        }
        if (kind === "group") {
          if (!project.groupRoles || !(subjectId in project.groupRoles)) {
            return unknownSubject();
          }
          const { [subjectId]: _removed, ...rest } = project.groupRoles;
          project.groupRoles = rest;
          return demoNoContent();
        }
        return notFound();
      }),
    },
  ];
};
