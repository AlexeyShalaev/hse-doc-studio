import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createDemoRouter } from "@shared/api/demo";
import { gitDemoRoutes, resetWorld } from "./routes";
import { SCENARIOS } from "./scenarios";

// Демо-API (VITE_GIT_DEMO=1) и настоящий бэкенд обязаны отдавать одну форму:
// иначе интерфейс, проверенный на демо, ломается на живых ответах. Живые ответы
// лежат в contracts/git-sync/live (их снимает backend-тест test_live_responses.py).

const LIVE = join(
  import.meta.dirname,
  ...Array<string>(5).fill(".."),
  "contracts",
  "git-sync",
  "live",
);
const router = createDemoRouter(gitDemoRoutes);
const PROJECT = "22222222-2222-4222-8222-222222222222";

// Ключи этих объектов задаёт содержимое (части текста, поля JSON, виды коммитов), а не контракт.
const DYNAMIC_KEYS = new Set(["resolution", "kinds"]);

// Пути ключей без значений. Ключи со значением null считаются отсутствующими: схемы фронтенда принимают оба вида.
const keyPaths = (value: unknown, prefix = ""): string[] => {
  if (Array.isArray(value)) {
    return value.flatMap((item) => keyPaths(item, `${prefix}[]`));
  }
  if (value === null || typeof value !== "object") return [];
  return Object.entries(value as Record<string, unknown>)
    .filter(([, child]) => child !== null)
    .flatMap(([key, child]) => {
      const path = prefix === "" ? key : `${prefix}.${key}`;
      return DYNAMIC_KEYS.has(key) ? [path] : [path, ...keyPaths(child, path)];
    });
};

const liveBodies = (schema: string): unknown[] =>
  readdirSync(join(LIVE, schema))
    .filter((file) => file.endsWith(".json"))
    .map((file): unknown =>
      JSON.parse(readFileSync(join(LIVE, schema, file), "utf8")),
    );

const demo = async (
  method: "GET" | "POST" | "PUT",
  path: string,
  body: unknown = null,
  query: Record<string, string> = {},
): Promise<unknown> => {
  const found = router.match(method, path);
  if (!found) throw new Error(`no demo route for ${method} ${path}`);
  const response = await found.handler({
    method,
    path,
    params: found.params,
    query,
    body,
    forward: () => Promise.reject(new Error("no real backend in tests")),
  });
  return response.data;
};

const union = (bodies: unknown[]): Set<string> =>
  new Set(bodies.flatMap((body) => keyPaths(body)));

// Поля, которые бэкенд присылает, а демо нет: интерфейс, проверенный на демо, их не видел. Обратное (демо
// богаче снимков) не расхождение: снимок сценария не охватывает все варианты, например ошибку или доступ.
const missingInDemo = (live: Set<string>, fake: Set<string>): string[] =>
  [...live].filter((path) => !fake.has(path)).sort();

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-10-26T10:00:00Z"));
});

afterEach(() => {
  vi.useRealTimers();
});

describe("демо и настоящий бэкенд: одна форма ответов", () => {
  it("состояние GET /projects/{id}/git", async () => {
    const fake: unknown[] = [];
    for (const scenario of SCENARIOS) {
      resetWorld(scenario.id);
      fake.push(await demo("GET", `/projects/${PROJECT}/git`));
    }
    expect(missingInDemo(union(liveBodies("GitStatus")), union(fake))).toEqual(
      [],
    );
  });

  it("сессия конфликтов и разбор файла", async () => {
    resetWorld("conflicts");
    const plain = await demo("GET", `/projects/${PROJECT}/git/conflicts`);
    // Черновик решения появляется после PUT /conflicts/draft: живой снимок есть и с ним.
    const first = (plain as { files: { path: string }[] }).files[0]?.path ?? "";
    await demo("PUT", `/projects/${PROJECT}/git/conflicts/draft`, {
      resolutions: { [first]: { kind: "file", choice: "mine" } },
    });
    const session = await demo("GET", `/projects/${PROJECT}/git/conflicts`);
    expect(
      missingInDemo(
        union(liveBodies("ConflictSession")),
        union([plain, session]),
      ),
    ).toEqual([]);
    const files = (session as { files: { path: string }[] }).files;
    const details = await Promise.all(
      files.map((file) =>
        demo("GET", `/projects/${PROJECT}/git/conflicts/file`, null, {
          path: file.path,
        }),
      ),
    );
    // Вид файла выбирает kind: поля каждого вида есть и у демо.
    const kindOf = (body: unknown): string | undefined =>
      (body as { kind?: string }).kind;
    const demoKinds = new Set(details.map(kindOf));
    for (const kind of new Set(liveBodies("ConflictFileDetail").map(kindOf))) {
      expect(demoKinds, kind).toContain(kind);
      const live = liveBodies("ConflictFileDetail").filter(
        (body) => kindOf(body) === kind,
      );
      const fake = details.filter((detail) => kindOf(detail) === kind);
      expect(missingInDemo(union(live), union(fake)), kind).toEqual([]);
    }
  });

  it("проверка адреса POST /git/remote/probe", async () => {
    resetWorld("not_connected");
    const fake = await Promise.all(
      ["empty", "plain", "offline"].map((word) =>
        demo("POST", "/git/remote/probe", {
          url: `https://github.com/team/${word}.git`,
          credential_id: null,
          project_id: PROJECT,
        }),
      ),
    );
    expect(missingInDemo(union(liveBodies("Probe")), union(fake))).toEqual([]);
  });
});
