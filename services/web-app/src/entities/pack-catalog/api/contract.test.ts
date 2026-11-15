import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import type { ZodType } from "zod";
import { PACK_CATALOG_ERROR_CODES, isPackCatalogErrorCode } from "./errorCodes";
import {
  ApplySourceRequestSchema,
  CatalogApplySchema,
  CatalogCheckSchema,
  CatalogErrorBodySchema,
  CatalogEventListSchema,
  CatalogOverviewSchema,
  CatalogSourceSchema,
  CreateGitSourceRequestSchema,
  UpdateSourceRequestSchema,
  WorkspaceCatalogCheckRequestSchema,
  WorkspaceCatalogSchema,
} from "./schemas";

// Контракт «Каталогов паков»: те же эталоны из contracts/pack-catalog разбирает и
// бэкенд-тест (tests/unit/contract/test_pack_catalog_contract.py).

const REPO = join(import.meta.dirname, "..", "..", "..", "..", "..", "..");
const CONTRACT = join(REPO, "contracts", "pack-catalog");
const FIXTURES = join(CONTRACT, "fixtures");
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

const SCHEMAS: Record<string, ZodType> = {
  ApplySourceRequest: ApplySourceRequestSchema,
  CatalogApply: CatalogApplySchema,
  CatalogCheck: CatalogCheckSchema,
  CatalogErrorBody: CatalogErrorBodySchema,
  CatalogEventList: CatalogEventListSchema,
  CatalogOverview: CatalogOverviewSchema,
  CatalogSource: CatalogSourceSchema,
  CreateGitSourceRequest: CreateGitSourceRequestSchema,
  UpdateSourceRequest: UpdateSourceRequestSchema,
  WorkspaceCatalog: WorkspaceCatalogSchema,
  WorkspaceCatalogCheckRequest: WorkspaceCatalogCheckRequestSchema,
};

const readJson = (path: string): unknown =>
  JSON.parse(readFileSync(path, "utf8"));

const directories = readdirSync(FIXTURES, { withFileTypes: true })
  .filter((entry) => entry.isDirectory())
  .map((entry) => entry.name)
  .sort();

const fixtures = directories.flatMap((schema) =>
  readdirSync(join(FIXTURES, schema))
    .filter((file) => file.endsWith(".json"))
    .sort()
    .map((file) => ({
      schema,
      name: file.replace(/\.json$/, ""),
      body: readJson(join(FIXTURES, schema, file)),
    })),
);

describe("контракт каталогов паков: коды ошибок", () => {
  const codes = readJson(join(CONTRACT, "error_codes.json")) as string[];

  it("константа TS совпадает с error_codes.json", () => {
    expect([...PACK_CATALOG_ERROR_CODES]).toEqual(codes);
  });

  it.each(["ru", "en"])(
    "в локали %s есть сообщение для каждого кода",
    (lng) => {
      const messages = (
        readJson(join(LOCALES, lng, "errors.json")) as {
          code: Record<string, string | undefined>;
        }
      ).code;
      expect(codes.filter((code) => !messages[code]?.trim())).toEqual([]);
    },
  );

  it("хелпер различает свои и незнакомые коды", () => {
    expect(isPackCatalogErrorCode("revision_moved")).toBe(true);
    expect(isPackCatalogErrorCode("from_the_future")).toBe(false);
  });
});

describe("контракт каталогов паков: эталоны", () => {
  it("у каждого каталога эталонов есть схема", () => {
    expect(directories).toEqual(Object.keys(SCHEMAS).sort());
  });

  it.each(fixtures.map((f) => [`${f.schema}/${f.name}`, f] as const))(
    "%s разбирается zod без потерь",
    (_label, fixture) => {
      const schema = SCHEMAS[fixture.schema];
      if (!schema) throw new Error(`нет схемы для ${fixture.schema}`);
      const parsed = schema.safeParse(fixture.body);
      expect(parsed.success).toBe(true);
      expect(parsed.data).toEqual(fixture.body);
    },
  );
});
