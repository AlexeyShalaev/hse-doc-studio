import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import type { ZodType } from "zod";
import { PACK_STUDIO_ERROR_CODES, isPackStudioErrorCode } from "./errorCodes";
import {
  CreatePackServiceAccessRequestSchema,
  CreatePackStudioGrantRequestSchema,
  CreatePackWorkspaceRequestSchema,
  PackBranchRequestSchema,
  PackCiStatusSchema,
  PackCommitRequestSchema,
  PackCommitResponseSchema,
  PackDiffSchema,
  PackEditorHintsSchema,
  PackFileVersionSchema,
  PackGitSchema,
  PackLintRequestSchema,
  PackLintSchema,
  PackPreviewBuildSchema,
  PackPreviewOptionsSchema,
  PackPreviewStartSchema,
  PackProposeRequestSchema,
  PackProposeResponseSchema,
  PackServiceAccessListSchema,
  PackServiceAccessSchema,
  PackSignaturesPatchRequestSchema,
  PackSignaturesSchema,
  PackStartOverRequestSchema,
  PackStudioAdminSchema,
  PackStudioErrorBodySchema,
  PackStudioGrantSchema,
  PackStudioSectionSchema,
  PackTreeSchema,
  PackWorkspaceListSchema,
  PackWorkspaceSchema,
  PackYamlPatchRequestSchema,
  PackYamlPatchResponseSchema,
  StartPackPreviewRequestSchema,
  UpdatePackStudioAdminRequestSchema,
  UpdatePackStudioSectionRequestSchema,
} from "./schemas";

// Контракт Студии шаблонов: те же эталоны из contracts/pack-studio разбирает и
// бэкенд-тест (tests/unit/contract/test_pack_studio_contract.py).

const REPO = join(import.meta.dirname, "..", "..", "..", "..", "..", "..");
const CONTRACT = join(REPO, "contracts", "pack-studio");
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
  PackStudioSection: PackStudioSectionSchema,
  UpdatePackStudioSectionRequest: UpdatePackStudioSectionRequestSchema,
  PackWorkspace: PackWorkspaceSchema,
  PackWorkspaceList: PackWorkspaceListSchema,
  CreatePackWorkspaceRequest: CreatePackWorkspaceRequestSchema,
  PackTree: PackTreeSchema,
  PackFileVersion: PackFileVersionSchema,
  PackYamlPatchRequest: PackYamlPatchRequestSchema,
  PackYamlPatchResponse: PackYamlPatchResponseSchema,
  PackStudioErrorBody: PackStudioErrorBodySchema,
  PackStudioGrant: PackStudioGrantSchema,
  PackStudioAdmin: PackStudioAdminSchema,
  UpdatePackStudioAdminRequest: UpdatePackStudioAdminRequestSchema,
  CreatePackStudioGrantRequest: CreatePackStudioGrantRequestSchema,
  PackLintRequest: PackLintRequestSchema,
  PackLint: PackLintSchema,
  PackEditorHints: PackEditorHintsSchema,
  PackPreviewOptions: PackPreviewOptionsSchema,
  StartPackPreviewRequest: StartPackPreviewRequestSchema,
  PackPreviewBuild: PackPreviewBuildSchema,
  PackPreviewStart: PackPreviewStartSchema,
  PackGit: PackGitSchema,
  PackDiff: PackDiffSchema,
  PackBranchRequest: PackBranchRequestSchema,
  PackCommitRequest: PackCommitRequestSchema,
  PackCommitResponse: PackCommitResponseSchema,
  PackProposeRequest: PackProposeRequestSchema,
  PackProposeResponse: PackProposeResponseSchema,
  PackCiStatus: PackCiStatusSchema,
  PackStartOverRequest: PackStartOverRequestSchema,
  PackServiceAccess: PackServiceAccessSchema,
  PackServiceAccessList: PackServiceAccessListSchema,
  CreatePackServiceAccessRequest: CreatePackServiceAccessRequestSchema,
  PackSignatures: PackSignaturesSchema,
  PackSignaturesPatchRequest: PackSignaturesPatchRequestSchema,
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

describe("контракт Студии шаблонов: коды ошибок", () => {
  const codes = readJson(join(CONTRACT, "error_codes.json")) as string[];

  it("константа TS совпадает с error_codes.json", () => {
    expect([...PACK_STUDIO_ERROR_CODES]).toEqual(codes);
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
    expect(isPackStudioErrorCode("version_released")).toBe(true);
    expect(isPackStudioErrorCode("from_the_future")).toBe(false);
  });
});

describe("контракт Студии шаблонов: эталоны", () => {
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
