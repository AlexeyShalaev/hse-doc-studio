import { describe, expect, it } from "vitest";
import { buildCloudList } from "./cloudList";
import type { CloudProject, CloudServer } from "./gitServer.schema";

const ANNA = "11111111-1111-4111-8111-111111111111";
const BORIS = "22222222-2222-4222-8222-222222222222";

const project = (
  id: string,
  over: Partial<CloudProject> = {},
): CloudProject => ({
  id,
  name: `П ${id.slice(0, 2)}`,
  owner_name: "Анна",
  role: "owner",
  can_push: true,
  updated_at: null,
  is_local: false,
  ...over,
});

const server = (over: Partial<CloudServer> = {}): CloudServer => {
  const projects = over.projects ?? [];
  return {
    credential_id: "cred",
    server_url: "https://studio.example.org",
    host: "studio.example.org",
    state: "ok",
    total: projects.length,
    ...over,
    projects,
  };
};

describe("buildCloudList", () => {
  it("shows only the projects that are not open here as cloud cards", () => {
    const view = buildCloudList(
      [server({ projects: [project(ANNA), project(BORIS)] })],
      new Set([ANNA]),
    );
    expect(view.remote.map((entry) => entry.project.id)).toEqual([BORIS]);
    expect([...view.linked.keys()]).toEqual([ANNA]);
  });

  it("trusts the backend mark as well as the local list", () => {
    const view = buildCloudList(
      [server({ projects: [project(ANNA, { is_local: true })] })],
      new Set(),
    );
    expect(view.remote).toEqual([]);
    expect(view.linked.get(ANNA)?.host).toBe("studio.example.org");
  });

  it("matches ids regardless of case", () => {
    const view = buildCloudList(
      [server({ projects: [project(ANNA.toUpperCase())] })],
      new Set([ANNA]),
    );
    expect(view.remote).toEqual([]);
  });

  it("lists a project of two servers once", () => {
    const view = buildCloudList(
      [
        server({ host: "a.example.org", projects: [project(ANNA)] }),
        server({ host: "b.example.org", projects: [project(ANNA)] }),
      ],
      new Set(),
    );
    expect(view.remote).toHaveLength(1);
    expect(view.remote[0]?.server.host).toBe("a.example.org");
  });

  it.each(["expired", "revoked", "unreachable"] as const)(
    "keeps a %s server out of the projects and reports it",
    (state) => {
      const view = buildCloudList(
        [server({ state, projects: [project(ANNA)] })],
        new Set(),
      );
      expect(view.remote).toEqual([]);
      expect(view.problems.map((s) => s.state)).toEqual([state]);
    },
  );

  it("reports empty and truncated servers", () => {
    const view = buildCloudList(
      [
        server({ host: "empty.example.org" }),
        server({
          host: "big.example.org",
          projects: [project(ANNA)],
          total: 9,
        }),
      ],
      new Set(),
    );
    expect(view.empty.map((s) => s.host)).toEqual(["empty.example.org"]);
    expect(view.truncated.map((s) => s.host)).toEqual(["big.example.org"]);
  });

  it("is empty without servers", () => {
    expect(buildCloudList([], new Set()).remote).toEqual([]);
  });
});
