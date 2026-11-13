import { existsSync, readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import type { ZodError } from "zod";

import { SchemaParseError } from "@shared/api/parse";
import { CONTRACT_SCHEMAS } from "./contractSchemas";
import { BootstrapSchema, ServerSetupSettingsRequestSchema } from "./schemas";

// Контракт серверного режима: те же эталонные JSON из contracts/server разбирает и backend-тест
// (tests/unit/contract/test_server_contract.py). Форму меняют так: сначала эталоны, затем обе
// стороны и оба набора тестов в одном коммите.
//
// contracts/server/next: эталоны, у которых zod-схема фронтенда уже есть, а модели бэкенда ещё
// нет (фронтовый срез раньше бэкендового, README контракта). Их разбирает только этот тест:
// файл next/<Схема>/<вариант>.json заменяет одноимённый из fixtures или добавляет вариант.
// Эталоны fixtures, которые next заменил, остаются формой нынешнего сервера: фронтенд обязан
// их разбирать, пока бэкенд не перешёл. Сейчас в `next` задача подписанта с метками даты
// (signing-route.md, 14.7), её ждёт R23.

const REPO = join(import.meta.dirname, "..", "..", "..", "..", "..", "..");
const CONTRACT = join(REPO, "contracts", "server");
const FIXTURES = join(CONTRACT, "fixtures");
const NEXT = join(CONTRACT, "next");
const LOCALES = join(
  REPO,
  "services",
  "web-app",
  "src",
  "shared",
  "lib",
  "i18n",
  "locales",
);

const readJson = (path: string): unknown =>
  JSON.parse(readFileSync(path, "utf8"));
const asRecord = (value: unknown): Record<string, unknown> =>
  value as Record<string, unknown>;

type Fixture = { schema: string; name: string; body: unknown };

const dirsOf = (root: string): string[] =>
  existsSync(root)
    ? readdirSync(root, { withFileTypes: true })
        .filter((entry) => entry.isDirectory())
        .map((entry) => entry.name)
    : [];

const filesOf = (root: string, schema: string): string[] =>
  existsSync(join(root, schema))
    ? readdirSync(join(root, schema)).filter((file) => file.endsWith(".json"))
    : [];

const directories = [...new Set([...dirsOf(FIXTURES), ...dirsOf(NEXT)])].sort();

const fixtures: Fixture[] = directories.flatMap((schema) =>
  [...new Set([...filesOf(FIXTURES, schema), ...filesOf(NEXT, schema)])]
    .sort()
    .map((file) => ({
      schema,
      name: file.replace(/\.json$/, ""),
      body: readJson(
        join(
          filesOf(NEXT, schema).includes(file) ? NEXT : FIXTURES,
          schema,
          file,
        ),
      ),
    })),
);

/** Эталоны нынешнего сервера, которые next заменил новой формой. */
const replaced: Fixture[] = dirsOf(NEXT).flatMap((schema) =>
  filesOf(NEXT, schema)
    .filter((file) => filesOf(FIXTURES, schema).includes(file))
    .sort()
    .map((file) => ({
      schema,
      name: file.replace(/\.json$/, ""),
      body: readJson(join(FIXTURES, schema, file)),
    })),
);

describe("контракт server: коды ошибок", () => {
  const codes = readJson(join(CONTRACT, "error_codes.json")) as string[];

  it("коды уникальны", () => {
    expect(new Set(codes).size).toBe(codes.length);
  });

  it.each(["ru", "en"])(
    "в локали %s есть сообщение для каждого кода",
    (lng) => {
      const messages = asRecord(
        asRecord(readJson(join(LOCALES, lng, "errors.json"))).code,
      ) as Record<string, string | undefined>;
      expect(codes.filter((code) => !messages[code]?.trim())).toEqual([]);
    },
  );

  it("коды из эталонов ошибок есть в каталоге", () => {
    const used = fixtures
      .filter((f) => f.schema === "AuthErrorBody")
      .map((f) => asRecord(f.body).code as string);
    expect(used.filter((code) => !codes.includes(code))).toEqual([]);
  });
});

describe("контракт server: эталоны", () => {
  it("у каждого каталога эталонов есть схема", () => {
    expect(directories).toEqual(Object.keys(CONTRACT_SCHEMAS).sort());
  });

  it.each(fixtures.map((f) => [`${f.schema}/${f.name}`, f] as const))(
    "%s разбирается zod без потерь",
    (_label, fixture) => {
      const schema = CONTRACT_SCHEMAS[fixture.schema];
      if (!schema) throw new Error(`нет схемы для ${fixture.schema}`);
      const parsed = schema.safeParse(fixture.body);
      expect(parsed.success).toBe(true);
      expect(parsed.data).toEqual(fixture.body);
    },
  );

  it.each(replaced.map((f) => [`${f.schema}/${f.name}`, f] as const))(
    "%s в форме нынешнего сервера разбирается (до слияния бэкенда)",
    (_label, fixture) => {
      const schema = CONTRACT_SCHEMAS[fixture.schema];
      expect(schema?.safeParse(fixture.body).success).toBe(true);
    },
  );

  it.each(
    fixtures
      .filter((f) => !Array.isArray(f.body))
      .map((f) => [`${f.schema}/${f.name}`, f] as const),
  )("%s: лишнее поле отвергается", (_label, fixture) => {
    const schema = CONTRACT_SCHEMAS[fixture.schema];
    const body = { ...asRecord(fixture.body), surprise: 1 };
    expect(schema?.safeParse(body).success).toBe(false);
  });

  it("неизвестный режим даёт SchemaParseError", () => {
    const body = {
      ...asRecord(
        fixtures.find((f) => f.schema === "Bootstrap" && f.name === "local")
          ?.body,
      ),
      mode: "cloud",
    };
    const result = BootstrapSchema.safeParse(body);
    expect(result.success).toBe(false);
    const error = new SchemaParseError(
      result.error as ZodError,
      body,
      "/api/v1/session/bootstrap",
      "GET",
    );
    expect(error.name).toBe("SchemaParseError");
  });

  it("эталоны bootstrap покрывают режимы и состояния", () => {
    const boots = fixtures
      .filter((f) => f.schema === "Bootstrap")
      .map((f) => asRecord(f.body));
    expect(new Set(boots.map((b) => b.mode))).toEqual(
      new Set(["local", "server"]),
    );
    expect(new Set(boots.map((b) => b.setup_state))).toEqual(
      new Set(["needs_admin", "ready"]),
    );
  });

  it("режим domains в мастере требует хотя бы один домен", () => {
    const body = {
      ...asRecord(
        fixtures.find(
          (f) =>
            f.schema === "ServerSetupSettingsRequest" && f.name === "domains",
        )?.body,
      ),
      registration_domains: [" @ "],
    };
    expect(ServerSetupSettingsRequestSchema.safeParse(body).success).toBe(
      false,
    );
  });

  it("проверки окружения мастера покрывают ok, fail и not_configured", () => {
    const statuses = fixtures
      .filter((f) => f.schema === "ServerSetupEnvironment")
      .flatMap((f) => asRecord(f.body).checks as { status: string }[])
      .map((c) => c.status);
    expect(new Set(statuses)).toEqual(
      new Set(["ok", "fail", "not_configured"]),
    );
  });
});
