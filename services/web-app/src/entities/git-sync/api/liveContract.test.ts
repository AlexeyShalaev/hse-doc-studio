import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import {
  GIT_OPERATION_KINDS,
  GIT_OPERATION_PHASES,
  GIT_OPERATION_STATUSES,
  GIT_SYNC_OUTCOMES,
  GIT_UI_STATES,
  isGitErrorCode,
} from "@entities/git-sync";
import { CONTRACT_SCHEMAS } from "./contractSchemas";

// Ответы настоящего бэкенда против zod-схем фронтенда. Тела снимает backend-тест
// services/api/tests/integration/api/git_sync/test_live_responses.py (двух Студий,
// локальные репозитории, настоящий git) и кладёт нормализованными в
// contracts/git-sync/live. Бэкенд при этом проверяет их своими строгими
// моделями, фронтенд здесь своими схемами: расхождение любой из сторон видно
// сразу, без запуска обоих сервисов. Обновить снимки: HSE_UPDATE_LIVE=1 у
// backend-теста.

const REPO = join(import.meta.dirname, "..", "..", "..", "..", "..", "..");
const CONTRACT = join(REPO, "contracts", "git-sync");
const FIXTURES = join(CONTRACT, "fixtures");
const LIVE = join(CONTRACT, "live");

type Snapshot = { schema: string; name: string; body: unknown };

const readJson = (path: string): unknown =>
  JSON.parse(readFileSync(path, "utf8"));

const readDirectory = (root: string): Snapshot[] =>
  readdirSync(root, { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    .map((entry) => entry.name)
    .sort()
    .flatMap((schema) =>
      readdirSync(join(root, schema))
        .filter((file) => file.endsWith(".json"))
        .sort()
        .map((file) => ({
          schema,
          name: file.replace(/\.json$/, ""),
          body: readJson(join(root, schema, file)),
        })),
    );

const live = readDirectory(LIVE);
const fixtures = readDirectory(FIXTURES);

const bodiesOf = (schema: string): Record<string, unknown>[] =>
  live
    .filter((snapshot) => snapshot.schema === schema)
    .map((snapshot) => snapshot.body as Record<string, unknown>);

const asRecord = (value: unknown): Record<string, unknown> =>
  value as Record<string, unknown>;

// Ключи этих объектов задаёт содержимое (части текста, поля JSON, виды коммитов), а не контракт.
const DYNAMIC_KEYS = new Set(["resolution", "kinds"]);

// Все вложенные объекты тела: у каждого свой набор ключей.
const objectsOf = (value: unknown): Record<string, unknown>[] => {
  if (Array.isArray(value)) return value.flatMap(objectsOf);
  if (value === null || typeof value !== "object") return [];
  const record = value as Record<string, unknown>;
  return [record, ...Object.values(record).flatMap(objectsOf)];
};

// Пути ключей без значений: `remote.credential.id`. Списки схлопнуты в `[]`.
const keyPaths = (value: unknown, prefix = ""): string[] => {
  if (Array.isArray(value)) {
    return value.flatMap((item) => keyPaths(item, `${prefix}[]`));
  }
  if (value === null || typeof value !== "object") return [];
  return Object.entries(value as Record<string, unknown>).flatMap(
    ([key, child]) => {
      const path = prefix === "" ? key : `${prefix}.${key}`;
      return DYNAMIC_KEYS.has(key) ? [path] : [path, ...keyPaths(child, path)];
    },
  );
};

describe("контракт git-sync: живые ответы бэкенда", () => {
  it("снимки есть, и у каждого каталога есть схема", () => {
    expect(live.length).toBeGreaterThan(40);
    const directories = [...new Set(live.map((snapshot) => snapshot.schema))];
    expect(directories.filter((name) => !(name in CONTRACT_SCHEMAS))).toEqual(
      [],
    );
  });

  it.each(live.map((snapshot) => [snapshot.schema, snapshot.name] as const))(
    "%s/%s разбирается zod без потерь",
    (schemaName, name) => {
      const snapshot = live.find(
        (item) => item.schema === schemaName && item.name === name,
      );
      const schema = CONTRACT_SCHEMAS[schemaName];
      if (!snapshot || !schema) throw new Error(`нет схемы ${schemaName}`);
      const parsed = schema.safeParse(snapshot.body);
      expect(parsed.success).toBe(true);
      // zod отбрасывает неизвестные поля: равенство значит, что схема знает каждое поле ответа
      expect(parsed.data).toEqual(snapshot.body);
    },
  );

  it("набор полей ответа совпадает с набором в эталонах той же схемы", () => {
    // Эталоны содержат все поля, в том числе null: живой ответ не вправе терять или добавлять поля.
    const skipped = new Set(["GitErrorBody", "ConflictFileDetail"]);
    for (const snapshot of live) {
      if (skipped.has(snapshot.schema)) continue;
      const golden = fixtures
        .filter((item) => item.schema === snapshot.schema)
        .flatMap((item) => keyPaths(item.body));
      const extra = keyPaths(snapshot.body).filter(
        (path) => !golden.includes(path),
      );
      expect(extra, `${snapshot.schema}/${snapshot.name}`).toEqual([]);
    }
  });

  it("у каждого вида файла конфликта те же поля, что в эталонах", () => {
    for (const snapshot of live.filter(
      (s) => s.schema === "ConflictFileDetail",
    )) {
      const body = asRecord(snapshot.body);
      const golden = fixtures.find(
        (item) =>
          item.schema === snapshot.schema &&
          asRecord(item.body).kind === body.kind,
      );
      expect(Object.keys(body).sort(), snapshot.name).toEqual(
        Object.keys(asRecord(golden?.body)).sort(),
      );
    }
  });

  it("состояния, операции и исходы лежат в закрытых списках контракта", () => {
    const states = bodiesOf("GitStatus").map((body) => body.ui_state);
    expect(new Set(states)).toEqual(new Set(GIT_UI_STATES));
    for (const operation of bodiesOf("Operation")) {
      expect(GIT_OPERATION_KINDS).toContain(operation.kind);
      expect(GIT_OPERATION_STATUSES).toContain(operation.status);
      expect(GIT_OPERATION_PHASES).toContain(operation.phase);
      const result = asRecord(operation.result ?? {});
      if ("outcome" in result) {
        expect(GIT_SYNC_OUTCOMES).toContain(result.outcome);
      }
    }
    const outcomes = bodiesOf("Operation").flatMap((operation) => {
      const result = asRecord(operation.result ?? {});
      return typeof result.outcome === "string" ? [result.outcome] : [];
    });
    expect(new Set(outcomes)).toEqual(
      new Set(["pushed", "fast_forwarded", "merged", "conflicts"]),
    );
  });

  it("каждый код ошибки в ответах есть в закрытом списке", () => {
    const codes = live.flatMap((snapshot) =>
      objectsOf(snapshot.body).flatMap((node) =>
        typeof node.code === "string" && "detail" in node ? [node.code] : [],
      ),
    );
    expect(codes.length).toBeGreaterThanOrEqual(4);
    expect(codes.filter((code) => !isGitErrorCode(code))).toEqual([]);
  });

  it("секреты не попадают в ответы", () => {
    const text = JSON.stringify(live.map((snapshot) => snapshot.body));
    expect(text).not.toContain("demo-token");
    const keys = live.flatMap((snapshot) => keyPaths(snapshot.body));
    for (const forbidden of ["token", "password", "private_key"]) {
      expect(
        keys.filter(
          (path) => path === forbidden || path.endsWith(`.${forbidden}`),
        ),
      ).toEqual([]);
    }
  });
});
