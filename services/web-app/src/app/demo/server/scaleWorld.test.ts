import { beforeAll, describe, expect, it } from "vitest";
import { createDemoRouter } from "@shared/api/demo";
import type { DemoResponse } from "@shared/api/demo";
import { activateServerScenario } from "./index";
import { serverAdminDemoRoutes, setServerDemoActive } from "./routes";
import { SCALE, createScaleWorld } from "./scaleWorld";

// Большой мир (admin_scale) и единый контракт списков в демо: страницы с total,
// поиск, фильтры, сортировка, курсор журнала и пикеры.

const router = createDemoRouter(serverAdminDemoRoutes);

type Page = { items: Record<string, unknown>[]; total: number };
type Log = { items: { id: number }[]; next_cursor: string | null };

const get = async (url: string): Promise<DemoResponse> => {
  const [path = "", search = ""] = url.split("?");
  const query: Record<string, string | string[]> = {};
  new URLSearchParams(search).forEach((value, key) => {
    const current = query[key];
    query[key] =
      current === undefined
        ? value
        : Array.isArray(current)
          ? [...current, value]
          : [current, value];
  });
  const found = router.match("GET", path);
  if (!found) throw new Error(`no demo route GET ${path}`);
  return found.handler({
    method: "GET",
    path,
    params: found.params,
    query,
    body: undefined,
    forward: () => Promise.reject(new Error("forward")),
  });
};
const json = async <T>(url: string): Promise<T> => {
  const res = await get(url);
  expect(res.status, url).toBe(200);
  return res.data as T;
};

describe("большой мир демо", () => {
  it("строится детерминированно и в заданных объёмах", () => {
    const started = performance.now();
    const a = createScaleWorld(Date.UTC(2026, 9, 30));
    const elapsed = performance.now() - started;
    const b = createScaleWorld(Date.UTC(2026, 9, 30));
    expect(a.people.users).toHaveLength(SCALE.people);
    expect(a.orgs.orgs).toHaveLength(SCALE.orgs);
    expect(a.orgs.orgs.reduce((n, o) => n + o.groups.length, 0)).toBe(
      SCALE.groups,
    );
    expect(a.ops.runners).toHaveLength(SCALE.runners);
    expect(a.ops.jobs).toHaveLength(SCALE.jobs);
    expect(a.people.invitations).toHaveLength(SCALE.invitations);
    expect(a.people.archive?.count).toBe(SCALE.audit);
    expect(new Set(a.people.users.map((u) => u.email)).size).toBe(SCALE.people);
    expect(b.people.users[500]).toEqual(a.people.users[500]);
    expect(b.people.archive?.at(1234)).toEqual(a.people.archive?.at(1234));
    // Мир строится при открытии сценария: держим его быстрым.
    expect(elapsed).toBeLessThan(3000);
  });
});

describe("контракт списков в демо", () => {
  beforeAll(() => {
    setServerDemoActive(true);
    activateServerScenario("admin_scale");
  });

  it("люди: страница, total, поиск, фильтр и сортировка", async () => {
    const all = await json<Page>("/users?limit=50&offset=0");
    expect(all.items).toHaveLength(50);
    expect(all.total).toBe(SCALE.people);
    const active = await json<Page>(
      "/users?limit=25&status=active&status=disabled&sort=name",
    );
    expect(active.total).toBeLessThan(SCALE.people);
    const names = active.items.map((u) => String(u.name));
    expect(names).toEqual(
      [...names].sort((x, y) =>
        x.localeCompare(y, "ru", { sensitivity: "base" }),
      ),
    );
    const found = await json<Page>("/users?limit=50&q=%20ИВАНОВ%20");
    expect(found.total).toBeGreaterThan(0);
    expect(
      found.items.every((u) =>
        `${String(u.name)} ${String(u.email)}`.toLowerCase().includes("иванов"),
      ),
    ).toBe(true);
    const facets = await json<{ status: Record<string, number> }>(
      "/users/facets?q=иванов",
    );
    expect(Object.values(facets.status).reduce((n, x) => n + x, 0)).toBe(
      found.total,
    );
  });

  it("неверные параметры дают 422", async () => {
    expect((await get("/users?limit=500")).status).toBe(422);
    expect((await get("/users?sort=password")).status).toBe(422);
    expect((await get("/users?status=root")).status).toBe(422);
    expect((await get(`/users?q=${"a".repeat(201)}`)).status).toBe(422);
    expect((await get("/audit?cursor=%%%")).status).toBe(422);
  });

  it("журнал листается курсором без повторов и дыр", async () => {
    const first = await json<Log & { total_estimate: number | null }>(
      "/audit?limit=100",
    );
    expect(first.total_estimate).toBeGreaterThan(SCALE.audit);
    expect(first.next_cursor).not.toBeNull();
    const second = await json<Log>(
      `/audit?limit=100&cursor=${String(first.next_cursor)}`,
    );
    const ids = [...first.items, ...second.items].map((e) => e.id);
    expect(new Set(ids).size).toBe(200);
    expect(ids).toEqual([...ids].sort((x, y) => y - x));
    const runner = await json<Log & { total_estimate: number | null }>(
      "/audit?limit=20&category=runner",
    );
    expect(runner.total_estimate).toBeNull();
    expect(runner.items.length).toBe(20);
  });

  it("очередь: курсор и фильтры по состоянию", async () => {
    const page = await json<{
      items: { state: string }[];
      next_cursor: string | null;
    }>("/queue?limit=30&state=failed");
    expect(page.items).toHaveLength(30);
    expect(page.items.every((j) => j.state === "failed")).toBe(true);
    expect(page.next_cursor).not.toBeNull();
  });

  it("организации и раннеры: страница по limit, без него массив", async () => {
    const orgs = await json<Page>("/orgs?limit=20&sort=-member_count");
    expect(orgs.total).toBe(SCALE.orgs);
    expect(orgs.items[0]?.member_count).toBe(6000);
    expect(Array.isArray(await json<unknown>("/orgs"))).toBe(true);
    const outdated = await json<Page>("/runners?limit=200&outdated=true");
    expect(outdated.items.every((r) => r.version !== "0.3.0")).toBe(true);
    const summary = await json<Record<string, number>>("/runners/summary");
    expect(summary.outdated).toBe(outdated.total);
  });

  it("пикер отдаёт до 20 и просит уточнить поиск", async () => {
    const people = await json<{ items: unknown[]; has_more: boolean }>(
      "/pickers/users?q=ова&limit=20",
    );
    expect(people.items).toHaveLength(20);
    expect(people.has_more).toBe(true);
    expect((await get("/pickers/users?limit=21")).status).toBe(422);
    const orgs = await json<{ items: { id: string }[] }>(
      "/pickers/orgs?q=студенты",
    );
    expect(orgs.items[0]?.id).toBeTruthy();
  });
});
