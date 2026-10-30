import type {
  ProjectAccessCandidate,
  ProjectAccessEntry,
  ProjectRole,
} from "@entities/session";
import type { DemoProject } from "./projects";
import { adminOrgsOf, type ServerDemoWorld } from "./world";

// Доступ к проектам в демо-мире: люди и группы с ролями. Итоговая роль человека
// это сильнейшая из прямой и тех, что даны его группам, как у настоящего сервера.

const ORDER: readonly ProjectRole[] = ["reader", "reviewer", "editor", "owner"];

const stronger = (
  a: ProjectRole | null,
  b: ProjectRole | null,
): ProjectRole | null => {
  if (a === null) return b;
  if (b === null) return a;
  return ORDER.indexOf(a) >= ORDER.indexOf(b) ? a : b;
};

export const effectiveRole = (
  world: ServerDemoWorld,
  project: DemoProject,
  userId: string | undefined,
): ProjectRole | null => {
  if (userId === undefined) return null;
  let role: ProjectRole | null = project.roles[userId] ?? null;
  const grants = project.groupRoles ?? {};
  for (const org of adminOrgsOf(world).orgs) {
    for (const group of org.groups) {
      const granted = grants[group.id];
      if (granted && group.member_ids.includes(userId)) {
        role = stronger(role, granted);
      }
    }
  }
  return role;
};

const emailOf = (world: ServerDemoWorld, userId: string): string | null =>
  adminOrgsOf(world).directory.find((u) => u.id === userId)?.email ?? null;

export const findGroup = (world: ServerDemoWorld, groupId: string) => {
  for (const org of adminOrgsOf(world).orgs) {
    const group = org.groups.find((g) => g.id === groupId);
    if (group) return { group, org };
  }
  return null;
};

/** Строки панели «Доступ»: владелец и организация закреплены, остальные меняются. */
export const accessEntries = (
  world: ServerDemoWorld,
  project: DemoProject,
): ProjectAccessEntry[] => {
  const owner = project.summary.owner;
  const entries: ProjectAccessEntry[] = [];
  if (owner.kind === "org") {
    entries.push({
      subject_kind: "org",
      subject_id: owner.id,
      name: owner.name,
      detail: null,
      role: "reader",
      locked: true,
    });
  }
  const userRows = Object.entries(project.roles)
    .filter(([id]) => !(owner.kind === "user" && owner.id === id))
    .flatMap(([id, role]) => {
      const person = adminOrgsOf(world).directory.find((u) => u.id === id);
      return person
        ? [
            {
              subject_kind: "user" as const,
              subject_id: id,
              name: person.name,
              detail: person.email,
              role,
              locked: role === "owner",
            },
          ]
        : [];
    });
  if (owner.kind === "user") {
    entries.unshift({
      subject_kind: "user",
      subject_id: owner.id,
      name: owner.name,
      detail: emailOf(world, owner.id),
      role: "owner",
      locked: true,
    });
  }
  const groupRows = Object.entries(project.groupRoles ?? {}).flatMap(
    ([id, role]) => {
      const found = findGroup(world, id);
      return found
        ? [
            {
              subject_kind: "group" as const,
              subject_id: id,
              name: found.group.name,
              detail: found.org.name,
              role,
              locked: false,
            },
          ]
        : [];
    },
  );
  const rest = (a: ProjectAccessEntry, b: ProjectAccessEntry) =>
    a.name.localeCompare(b.name, "ru");
  return [
    ...entries,
    ...userRows.filter((r) => r.locked).sort(rest),
    ...groupRows.sort(rest),
    ...userRows.filter((r) => !r.locked).sort(rest),
  ];
};

/** Кого можно добавить: люди и группы, которых в проекте ещё нет. */
export const accessCandidates = (
  world: ServerDemoWorld,
  project: DemoProject,
  query: string,
): ProjectAccessCandidate[] => {
  const needle = query.trim().toLowerCase();
  const owner = project.summary.owner;
  const hit = (...parts: (string | null)[]) =>
    needle === "" ||
    parts.some((part) => part?.toLowerCase().includes(needle) ?? false);
  const people: ProjectAccessCandidate[] = adminOrgsOf(world)
    .directory.filter(
      (u) =>
        !(u.id in project.roles) &&
        !(owner.kind === "user" && owner.id === u.id) &&
        hit(u.name, u.email),
    )
    .map((u) => ({
      subject_kind: "user",
      subject_id: u.id,
      name: u.name,
      detail: u.email,
    }));
  const groups: ProjectAccessCandidate[] = adminOrgsOf(world).orgs.flatMap(
    (org) =>
      org.groups
        .filter((g) => !(g.id in (project.groupRoles ?? {})) && hit(g.name))
        .map((g) => ({
          subject_kind: "group" as const,
          subject_id: g.id,
          name: g.name,
          detail: org.name,
        })),
  );
  return [...groups, ...people].slice(0, 12);
};
