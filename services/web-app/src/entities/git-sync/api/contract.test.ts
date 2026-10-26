import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import type { ZodType } from "zod";

import { VcsCommitSchema } from "@entities/vcs";
import {
  CloneDefaultsSchema,
  CloneRequestSchema,
  CreateCredentialRequestSchema,
  GitCredentialListSchema,
  GitCredentialSchema,
  GitHostListSchema,
  ProbeRequestSchema,
  ProbeSchema,
  ProbeUrlSchema,
  SecretsStatusSchema,
  SharedFolderSchema,
  TrustHostRequestSchema,
  UpdateCredentialRequestSchema,
} from "@entities/git-remote";
import {
  ProfileRequestSchema,
  ProfileSchema,
  ProfileValidationErrorSchema,
} from "@entities/profile";
import {
  CiPreviewSchema,
  CiRequestSchema,
  CiWriteRequestSchema,
  CiWriteSchema,
  CloneResultSchema,
  ConflictDiffSchema,
  ConflictFileDetailSchema,
  ConflictSessionSchema,
  ConnectRemoteRequestSchema,
  GIT_ERROR_CODES,
  GIT_OPERATION_KINDS,
  GIT_OPERATION_PHASES,
  GIT_OPERATION_STATUSES,
  GIT_SYNC_OUTCOMES,
  GIT_UI_STATES,
  GitContentsSchema,
  GitErrorBodySchema,
  GitStatusSchema,
  HistoryCommitExtrasSchema,
  HistoryFacetsSchema,
  OperationSchema,
  OperationStartedSchema,
  ResolveConflictsRequestSchema,
  SaveConflictDraftRequestSchema,
  SyncResultSchema,
  UpdateGitSettingsRequestSchema,
  gitErrorI18nKey,
  isGitErrorCode,
} from "@entities/git-sync";

// Контракт Git-синхронизации: те же эталонные JSON из contracts/git-sync разбирает
// и backend-тест (tests/unit/contract/test_git_sync_contract.py). Форму меняют так:
// сначала эталоны, затем обе стороны и оба набора тестов в одном коммите.

const REPO = join(import.meta.dirname, "..", "..", "..", "..", "..", "..");
const CONTRACT = join(REPO, "contracts", "git-sync");
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

const readJson = (path: string): unknown =>
  JSON.parse(readFileSync(path, "utf8"));

const HistoryCommitSchema = VcsCommitSchema.extend(
  HistoryCommitExtrasSchema.shape,
);

// Каталог эталонов -> схема, которой он обязан соответствовать.
const SCHEMAS: Record<string, ZodType> = {
  GitErrorBody: GitErrorBodySchema,
  ProfileValidationError: ProfileValidationErrorSchema,
  Profile: ProfileSchema,
  ProfileRequest: ProfileRequestSchema,
  GitCredential: GitCredentialSchema,
  GitCredentialList: GitCredentialListSchema,
  CreateCredentialRequest: CreateCredentialRequestSchema,
  UpdateCredentialRequest: UpdateCredentialRequestSchema,
  GitHostList: GitHostListSchema,
  TrustHostRequest: TrustHostRequestSchema,
  SecretsStatus: SecretsStatusSchema,
  SharedFolder: SharedFolderSchema,
  CloneDefaults: CloneDefaultsSchema,
  Probe: ProbeSchema,
  ProbeRequest: ProbeRequestSchema,
  OperationStarted: OperationStartedSchema,
  SyncResult: SyncResultSchema,
  CloneResult: CloneResultSchema,
  Operation: OperationSchema,
  CloneRequest: CloneRequestSchema,
  GitStatus: GitStatusSchema,
  ConnectRemoteRequest: ConnectRemoteRequestSchema,
  UpdateGitSettingsRequest: UpdateGitSettingsRequestSchema,
  GitContents: GitContentsSchema,
  ConflictSession: ConflictSessionSchema,
  ConflictFileDetail: ConflictFileDetailSchema,
  ConflictDiff: ConflictDiffSchema,
  ResolveConflictsRequest: ResolveConflictsRequestSchema,
  SaveConflictDraftRequest: SaveConflictDraftRequestSchema,
  CiRequest: CiRequestSchema,
  CiWriteRequest: CiWriteRequestSchema,
  CiPreview: CiPreviewSchema,
  CiWrite: CiWriteSchema,
  HistoryCommit: HistoryCommitSchema,
  HistoryFacets: HistoryFacetsSchema,
};

type Fixture = {
  schema: string;
  name: string;
  body: unknown;
};

const directories = readdirSync(FIXTURES, { withFileTypes: true })
  .filter((entry) => entry.isDirectory())
  .map((entry) => entry.name)
  .sort();

const fixtures: Fixture[] = directories.flatMap((schema) =>
  readdirSync(join(FIXTURES, schema))
    .filter((file) => file.endsWith(".json"))
    .sort()
    .map((file) => ({
      schema,
      name: file.replace(/\.json$/, ""),
      body: readJson(join(FIXTURES, schema, file)),
    })),
);

const bodiesOf = (schema: string): unknown[] =>
  fixtures.filter((f) => f.schema === schema).map((f) => f.body);

const asRecord = (value: unknown): Record<string, unknown> =>
  value as Record<string, unknown>;

describe("контракт git-sync: коды ошибок", () => {
  const codes = readJson(join(CONTRACT, "error_codes.json")) as string[];

  it("константа TS совпадает с error_codes.json", () => {
    expect([...GIT_ERROR_CODES]).toEqual(codes);
    expect(new Set(codes).size).toBe(codes.length);
  });

  it.each(["ru", "en"])(
    "в локали %s есть сообщение для каждого кода",
    (lng) => {
      const messages = asRecord(
        asRecord(readJson(join(LOCALES, lng, "errors.json"))).code,
      ) as Record<string, string | undefined>;
      const missing = codes.filter((code) => !messages[code]?.trim());
      expect(missing).toEqual([]);
    },
  );

  it("хелперы различают известные и незнакомые коды", () => {
    expect(isGitErrorCode("auth_failed")).toBe(true);
    expect(isGitErrorCode("from_the_future")).toBe(false);
    expect(gitErrorI18nKey("offline")).toBe("errors:code.offline");
    expect(gitErrorI18nKey("from_the_future")).toBeNull();
  });
});

describe("контракт git-sync: эталоны", () => {
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
      // zod отбрасывает неизвестные поля: равенство значит, что схема знает каждое поле эталона
      expect(parsed.data).toEqual(fixture.body);
    },
  );

  it("эталоны статуса покрывают все состояния кнопки", () => {
    const states = new Set(
      bodiesOf("GitStatus").map((b) => asRecord(b).ui_state),
    );
    expect(states).toEqual(new Set(GIT_UI_STATES));
  });

  it("эталоны операций покрывают виды, статусы и фазы", () => {
    const ops = bodiesOf("Operation").map(asRecord);
    expect(new Set(ops.map((o) => o.kind))).toEqual(
      new Set(GIT_OPERATION_KINDS),
    );
    expect(new Set(ops.map((o) => o.status))).toEqual(
      new Set(GIT_OPERATION_STATUSES),
    );
    expect(new Set(ops.map((o) => o.phase))).toEqual(
      new Set(GIT_OPERATION_PHASES),
    );
  });

  it("эталоны результата покрывают все исходы", () => {
    const outcomes = new Set(
      bodiesOf("SyncResult").map((b) => asRecord(b).outcome),
    );
    expect(outcomes).toEqual(new Set(GIT_SYNC_OUTCOMES));
  });

  it("результат операции различается по виду", () => {
    const sync = OperationSchema.parse(
      asRecord(fixtures.find((f) => f.name === "sync_pushed")?.body),
    );
    const clone = OperationSchema.parse(
      asRecord(fixtures.find((f) => f.name === "clone_succeeded")?.body),
    );
    expect(sync.result).toHaveProperty("outcome", "pushed");
    expect(clone.result).toHaveProperty("access", "full");
  });

  it("коды ошибок в эталонах входят в закрытый список", () => {
    const known = new Set<string>(GIT_ERROR_CODES);
    const seen: string[] = [];
    const visit = (value: unknown): void => {
      if (Array.isArray(value)) value.forEach(visit);
      else if (value && typeof value === "object") {
        const node = asRecord(value);
        if (typeof node.code === "string" && "detail" in node)
          seen.push(node.code);
        Object.values(node).forEach(visit);
      }
    };
    fixtures.forEach((f) => {
      visit(f.body);
    });
    expect(seen.length).toBeGreaterThan(0);
    expect(seen.filter((code) => !known.has(code))).toEqual([]);
  });
});

describe("контракт git-sync: векторы разбора адреса", () => {
  type UrlCase = {
    name: string;
    input:
      | string
      | { prefix: string; repeat: string; times: number; suffix: string };
    policy?: Record<string, boolean>;
    ok: boolean;
    url?: unknown;
    error?: string;
  };
  const cases = (
    readJson(join(CONTRACT, "url_cases.json")) as { cases: UrlCase[] }
  ).cases;
  const known = new Set<string>(GIT_ERROR_CODES);

  it("имена уникальны, политика и коды из допустимого набора", () => {
    expect(new Set(cases.map((c) => c.name)).size).toBe(cases.length);
    for (const c of cases) {
      expect(
        Object.keys(c.policy ?? {}).filter(
          (key) => key !== "allow_http" && key !== "allow_local",
        ),
      ).toEqual([]);
      if (c.ok) expect(ProbeUrlSchema.safeParse(c.url).success).toBe(true);
      else expect(known.has(c.error ?? "")).toBe(true);
    }
  });

  it("есть и допустимые адреса, и оба вида отказа", () => {
    expect(cases.some((c) => c.ok)).toBe(true);
    const errors = new Set(cases.filter((c) => !c.ok).map((c) => c.error));
    expect(errors).toEqual(new Set(["url_invalid", "url_scheme_forbidden"]));
  });
});
