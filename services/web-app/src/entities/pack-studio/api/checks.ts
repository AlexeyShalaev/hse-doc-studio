import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { apiClient, parseResp } from "@shared/api";
import type { PackVersionRef } from "./packStudioApi";
import { packStudioKeys } from "./queries";

// Файлы правил `checks/*.yaml` и `checks_version` формой (срез T14, contracts/pack-studio,
// раздел «Проверки»). Эталоны разбирают и эти схемы (contract.test.ts), и строгие модели
// бэкенда (api/schemas/pack_studio_checks.py).

const LocalizedSchema = z.record(z.string(), z.string());
const ReadOnlySchema = z.enum(["version_released", "releases_read_only"]);

export const PackChecksHeaderSchema = z.strictObject({
  label: LocalizedSchema,
  ref: LocalizedSchema,
  source: LocalizedSchema.optional(),
  url: z.string().max(1000).nullish(),
});

export const PackCheckRuleSchema = z.strictObject({
  id: z.string().min(1).max(160),
  title: LocalizedSchema,
  description: LocalizedSchema.optional(),
  category: z.string().max(64).nullish(),
  // null: все документы (`*`).
  applies_to: z.array(z.string()).nullish(),
  default_severity: z.enum(["info", "warn", "err"]),
  engine: z.string().min(1).max(32),
  params: z.record(z.string(), z.unknown()).optional(),
});

export const PackChecksSchema = z.strictObject({
  workspace_id: z.string(),
  pack: z.string(),
  template: z.string(),
  version: z.string(),
  documents: z.array(z.string()),
  files: z.array(
    z.strictObject({
      path: z.string(),
      name: z.string(),
      etag: z.string(),
      read_only: ReadOnlySchema.nullable(),
      header: PackChecksHeaderSchema,
      rules: z.array(
        z.strictObject({
          index: z.number().int(),
          entry: PackCheckRuleSchema.nullable(),
          // Параметры текстом YAML для правки движков без своих полей.
          params_yaml: z.string().nullable(),
          error: z.string().nullable(),
        }),
      ),
      error: z.string().nullable(),
    }),
  ),
  config: z.strictObject({
    path: z.string(),
    etag: z.string(),
    read_only: ReadOnlySchema.nullable(),
    disabled_categories: z.array(z.string()),
    disabled: z.array(z.string()),
    severity_override: z.record(z.string(), z.string()),
  }),
  engines: z.array(z.string()),
  structural_checks: z.array(z.string()),
});

export const PackChecksOpSchema = z.strictObject({
  op: z.enum([
    "set_header",
    "add_rule",
    "set_rule",
    "remove_rule",
    "move_rule",
  ]),
  header: PackChecksHeaderSchema.nullish(),
  index: z.number().int().min(0).nullish(),
  to: z.number().int().min(0).nullish(),
  rule: PackCheckRuleSchema.nullish(),
  // Параметры правила текстом YAML (движки без своих полей); заменяет `rule.params`.
  params_yaml: z.string().max(20000).nullish(),
});

export const PackChecksPatchRequestSchema = z.strictObject({
  ops: z.array(PackChecksOpSchema).min(1).max(50),
});

export const PackChecksConfigRequestSchema = z.strictObject({
  disabled_categories: z.array(z.string()).optional(),
  disabled: z.array(z.string()).optional(),
  severity_override: z
    .record(z.string(), z.enum(["info", "warn", "err", "skipped"]))
    .optional(),
});

export type PackChecks = z.infer<typeof PackChecksSchema>;
export type PackChecksFile = PackChecks["files"][number];
export type PackChecksHeader = z.infer<typeof PackChecksHeaderSchema>;
export type PackCheckRule = z.infer<typeof PackCheckRuleSchema>;
export type PackChecksOp = z.infer<typeof PackChecksOpSchema>;
export type PackChecksPatchRequest = z.infer<
  typeof PackChecksPatchRequestSchema
>;
export type PackChecksConfigRequest = z.infer<
  typeof PackChecksConfigRequestSchema
>;

const quiet = { silentError: true } as const;
const enc = encodeURIComponent;
const checksPath = (id: string, ref: PackVersionRef) =>
  `/pack-studio/workspaces/${enc(id)}/versions/${enc(ref.pack)}/${enc(ref.template)}/${enc(ref.version)}/checks`;
const ifMatch = (etag: string | null) =>
  etag ? { headers: { "If-Match": etag } } : {};

export const packChecksApi = {
  get: (id: string, ref: PackVersionRef): Promise<PackChecks> =>
    apiClient.get(checksPath(id, ref), quiet).then(parseResp(PackChecksSchema)),
  /** Правки файла правил с `If-Match` по его ETag: весь набор или ничего. */
  patchFile: (
    id: string,
    ref: PackVersionRef,
    name: string,
    body: PackChecksPatchRequest,
    etag: string | null,
  ): Promise<PackChecks> =>
    apiClient
      .patch(`${checksPath(id, ref)}/files/${enc(name)}`, body, {
        ...quiet,
        ...ifMatch(etag),
      })
      .then(parseResp(PackChecksSchema)),
  /** `checks_version` с `If-Match` по ETag `version.yaml`. */
  putConfig: (
    id: string,
    ref: PackVersionRef,
    body: PackChecksConfigRequest,
    etag: string | null,
  ): Promise<PackChecks> =>
    apiClient
      .put(`${checksPath(id, ref)}/config`, body, {
        ...quiet,
        ...ifMatch(etag),
      })
      .then(parseResp(PackChecksSchema)),
};

export const packChecksKeys = {
  of: (id: string, ref: PackVersionRef) =>
    [
      ...packStudioKeys.workspace(id),
      "checks-form",
      ref.pack,
      ref.template,
      ref.version,
    ] as const,
};

const EMPTY_REF: PackVersionRef = { pack: "", template: "", version: "" };

/** Файлы правил и `checks_version` версии (срез T14). */
export const usePackChecksForm = (id: string, ref: PackVersionRef | null) =>
  useQuery({
    queryKey: packChecksKeys.of(id, ref ?? EMPTY_REF),
    queryFn: () => packChecksApi.get(id, ref ?? EMPTY_REF),
    enabled: ref !== null,
  });

type ChecksEdit =
  | {
      kind: "file";
      name: string;
      body: PackChecksPatchRequest;
      etag: string | null;
    }
  | { kind: "config"; body: PackChecksConfigRequest; etag: string | null };

/** Правка проверок: ответ сразу ложится в кэш, записанный файл и git помечаются устаревшими. */
export const usePatchPackChecksForm = (id: string, ref: PackVersionRef) => {
  const client = useQueryClient();
  return useMutation({
    // Та же очередь, что у правок формы версии (T11): записи манифестов идут по одной.
    scope: { id: `pack-model:${id}` },
    mutationFn: (edit: ChecksEdit) =>
      edit.kind === "file"
        ? packChecksApi.patchFile(id, ref, edit.name, edit.body, edit.etag)
        : packChecksApi.putConfig(id, ref, edit.body, edit.etag),
    onSuccess: (data, edit) => {
      client.setQueryData(packChecksKeys.of(id, ref), data);
      // Модель общей формы версии берёт новый ETag манифеста и список файлов правил.
      void client.invalidateQueries({
        queryKey: packStudioKeys.model(id, ref),
      });
      const path =
        edit.kind === "file"
          ? data.files.find((f) => f.name === edit.name)?.path
          : data.config.path;
      if (path) {
        void client.invalidateQueries({
          queryKey: packStudioKeys.file(id, path),
        });
      }
      void client.invalidateQueries({ queryKey: packStudioKeys.git(id) });
    },
  });
};
