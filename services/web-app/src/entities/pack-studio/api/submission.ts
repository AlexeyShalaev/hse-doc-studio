import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { apiClient, parseResp } from "@shared/api";
import type { PackVersionRef } from "./packStudioApi";
import { packStudioKeys } from "./queries";

// Профили сдачи, пункты и порядок маршрута формой (срез T13, contracts/pack-studio,
// раздел «Точки сдачи»). Эталоны разбирают и эти схемы (contract.test.ts), и строгие
// модели бэкенда (api/schemas/pack_studio_submission.py).

const LocalizedSchema = z.record(z.string(), z.string());
const StepsSchema = z.array(z.array(z.string()));
const SignMethodSchema = z.enum(["image", "detached", "pades"]);
const KindSchema = z.enum(["research", "project"]);

export const PackSubmissionItemSchema = z.strictObject({
  doc_id: z.string().min(1).max(128),
  signatures: z.array(z.string()).max(16),
  // Нет записи у слота: любой способ.
  methods: z.record(z.string(), z.array(SignMethodSchema)),
  skip_if_nda: z.boolean(),
  // Пусто: оба вида работы.
  supported_kinds: z.array(KindSchema).max(2),
});

export const PackSubmissionExtraSchema = z.strictObject({
  source: z.string().min(1).max(512),
  output_name: z.string().max(255),
  format: z.string().max(32).nullable(),
  supported_kinds: z.array(KindSchema).max(2),
});

export const PackSubmissionWhenSchema = z.strictObject({
  person: z.enum(["supervisor", "co_supervisor", "academic_supervisor"]),
  role: z.enum(["university", "company"]).nullable(),
});

export const PackSubmissionSlotSchema = z.strictObject({
  doc_id: z.string().min(1).max(128),
  slot_id: z.string().min(1).max(64),
  when: PackSubmissionWhenSchema.nullable(),
  optional: z.boolean(),
});

const indexed = <T extends z.ZodType>(entry: T) =>
  z.strictObject({
    // Индекс в списке YAML; `entry` null, если лоадер запись не читает.
    index: z.number().int(),
    entry: entry.nullable(),
    error: z.string().nullable(),
  });

export const PackSubmissionProfileSchema = z.strictObject({
  index: z.number().int(),
  id: z.string().nullable(),
  name: LocalizedSchema,
  description: LocalizedSchema,
  deadline_hint: LocalizedSchema.nullable(),
  items: z.array(indexed(PackSubmissionItemSchema)),
  extra_items: z.array(indexed(PackSubmissionExtraSchema)),
  // null: ключа нет, действует порядок версии.
  signing_route: StepsSchema.nullable(),
  signing_slots: z.array(indexed(PackSubmissionSlotSchema)),
  error: z.string().nullable(),
});

export const PackSubmissionSchema = z.strictObject({
  workspace_id: z.string(),
  pack: z.string(),
  template: z.string(),
  version: z.string(),
  path: z.string(),
  etag: z.string(),
  read_only: z.enum(["version_released", "releases_read_only"]).nullable(),
  documents: z.array(z.string()),
  supported_kinds: z.array(KindSchema),
  has_nda: z.boolean(),
  slots: z.array(
    z.strictObject({
      id: z.string(),
      label: LocalizedSchema,
      applies_to: z.array(z.string()),
      required: z.boolean(),
      per_author: z.boolean(),
    }),
  ),
  forms: z.array(
    z.strictObject({
      id: z.string(),
      title: LocalizedSchema,
      source: z.string(),
      output_name: z.string(),
      format: z.string().nullable(),
      required_for_pack: z.boolean(),
    }),
  ),
  // null: ключа нет, действует встроенный порядок.
  route: StepsSchema.nullable(),
  builtin_route: StepsSchema,
  profiles: z.array(PackSubmissionProfileSchema),
});

export const PackProfileHeadSchema = z.strictObject({
  id: z.string().min(1).max(64),
  name: LocalizedSchema,
  description: LocalizedSchema.optional(),
  // null убирает подсказку срока.
  deadline_hint: LocalizedSchema.nullish(),
});

export const PackSubmissionOpSchema = z.strictObject({
  op: z.enum([
    "add_profile",
    "set_profile",
    "remove_profile",
    "move_profile",
    "set_profile_route",
    "add_entry",
    "set_entry",
    "remove_entry",
    "move_entry",
    "set_route",
  ]),
  profile: z.number().int().min(0).nullish(),
  head: PackProfileHeadSchema.nullish(),
  entries: z.enum(["items", "extra_items", "signing_slots"]).nullish(),
  index: z.number().int().min(0).nullish(),
  to: z.number().int().min(0).nullish(),
  item: PackSubmissionItemSchema.nullish(),
  extra: PackSubmissionExtraSchema.nullish(),
  slot: PackSubmissionSlotSchema.nullish(),
  steps: StepsSchema.nullish(),
});

export const PackSubmissionPatchRequestSchema = z.strictObject({
  ops: z.array(PackSubmissionOpSchema).min(1).max(50),
});

export const PackSubmissionRoutesRequestSchema = z.strictObject({
  example: z.string().max(255).nullish(),
  combination: z.record(z.string(), z.string()).optional(),
});

const PersonRoleSchema = z.enum([
  "author",
  "supervisor",
  "co_supervisor",
  "academic_supervisor",
]);

export const PackProfileRouteSchema = z.strictObject({
  id: z.string(),
  steps: z.array(
    z.array(
      z.strictObject({
        persona: z.string(),
        role: PersonRoleSchema,
        name: z.string(),
      }),
    ),
  ),
  pairs: z.array(
    z.strictObject({
      doc_id: z.string(),
      slot_id: z.string(),
      persona: z.string(),
      source: z.enum(["point", "preset"]),
      optional: z.boolean(),
      when: PackSubmissionWhenSchema.nullable(),
    }),
  ),
  skipped: z.array(
    z.strictObject({
      doc_id: z.string(),
      slot_id: z.string(),
      when: PackSubmissionWhenSchema.nullable(),
    }),
  ),
  may_add: z.array(z.strictObject({ doc_id: z.string(), slot_id: z.string() })),
  items_off: z.array(z.string()),
  order_source: z.enum(["profile", "version", "builtin"]),
  preset: z.boolean(),
});

export const PackSubmissionRoutesSchema = z.strictObject({
  example: z.string(),
  combination: z.record(z.string(), z.string()),
  profiles: z.array(PackProfileRouteSchema),
});

export type PackSubmission = z.infer<typeof PackSubmissionSchema>;
export type PackSubmissionProfile = z.infer<typeof PackSubmissionProfileSchema>;
export type PackSubmissionItem = z.infer<typeof PackSubmissionItemSchema>;
export type PackSubmissionExtra = z.infer<typeof PackSubmissionExtraSchema>;
export type PackSubmissionSlot = z.infer<typeof PackSubmissionSlotSchema>;
export type PackSubmissionWhen = z.infer<typeof PackSubmissionWhenSchema>;
export type PackSubmissionOp = z.infer<typeof PackSubmissionOpSchema>;
export type PackProfileHead = z.infer<typeof PackProfileHeadSchema>;
export type PackSubmissionPatchRequest = z.infer<
  typeof PackSubmissionPatchRequestSchema
>;
export type PackSubmissionRoutesRequest = z.infer<
  typeof PackSubmissionRoutesRequestSchema
>;
export type PackProfileRoute = z.infer<typeof PackProfileRouteSchema>;
export type PackSubmissionRoutes = z.infer<typeof PackSubmissionRoutesSchema>;

const quiet = { silentError: true } as const;
const enc = encodeURIComponent;
const submissionPath = (id: string, ref: PackVersionRef) =>
  `/pack-studio/workspaces/${enc(id)}/versions/${enc(ref.pack)}/${enc(ref.template)}/${enc(ref.version)}/submission`;

export const packSubmissionApi = {
  get: (id: string, ref: PackVersionRef): Promise<PackSubmission> =>
    apiClient
      .get(submissionPath(id, ref), quiet)
      .then(parseResp(PackSubmissionSchema)),
  /** Правки формы с `If-Match` по ETag `version.yaml`: весь набор или ничего. */
  patch: (
    id: string,
    ref: PackVersionRef,
    body: PackSubmissionPatchRequest,
    ifMatch: string | null,
  ): Promise<PackSubmission> =>
    apiClient
      .patch(submissionPath(id, ref), body, {
        ...quiet,
        headers: ifMatch ? { "If-Match": ifMatch } : {},
      })
      .then(parseResp(PackSubmissionSchema)),
  routes: (
    id: string,
    ref: PackVersionRef,
    body: PackSubmissionRoutesRequest,
  ): Promise<PackSubmissionRoutes> =>
    apiClient
      .post(`${submissionPath(id, ref)}/routes`, body, {
        ...quiet,
        timeout: 60_000,
      })
      .then(parseResp(PackSubmissionRoutesSchema)),
};

const refKey = (ref: PackVersionRef) =>
  [ref.pack, ref.template, ref.version] as const;

export const packSubmissionKeys = {
  all: (id: string) => [...packStudioKeys.workspace(id), "submission"] as const,
  of: (id: string, ref: PackVersionRef) =>
    [...packSubmissionKeys.all(id), ...refKey(ref)] as const,
  // Маршрут зависит от файлов версии и комбинации: `revision` меняется с каждой правкой.
  routes: (
    id: string,
    ref: PackVersionRef,
    revision: string,
    body: PackSubmissionRoutesRequest,
  ) =>
    [
      ...packSubmissionKeys.of(id, ref),
      "routes",
      revision,
      JSON.stringify(body),
    ] as const,
};

/** Профили сдачи версии (срез T13). */
export const usePackSubmission = (id: string, ref: PackVersionRef | null) =>
  useQuery({
    queryKey: packSubmissionKeys.of(
      id,
      ref ?? { pack: "", template: "", version: "" },
    ),
    queryFn: () =>
      packSubmissionApi.get(id, ref ?? { pack: "", template: "", version: "" }),
    enabled: ref !== null,
  });

/**
 * Правка формы: ответ сразу ложится в кэш, файл манифеста и git помечаются устаревшими.
 * `If-Match` берётся из последнего ответа.
 */
export const usePatchPackSubmission = (id: string, ref: PackVersionRef) => {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({
      body,
      etag,
    }: {
      body: PackSubmissionPatchRequest;
      etag: string | null;
    }) => packSubmissionApi.patch(id, ref, body, etag),
    onSuccess: (data) => {
      client.setQueryData(packSubmissionKeys.of(id, ref), data);
      void client.invalidateQueries({
        queryKey: packStudioKeys.file(id, data.path),
      });
      void client.invalidateQueries({ queryKey: packStudioKeys.git(id) });
    },
  });
};

/** «Маршрут в этой комбинации» каждого профиля; пересчёт после каждой правки версии. */
export const usePackSubmissionRoutes = (
  id: string,
  ref: PackVersionRef | null,
  revision: string,
  body: PackSubmissionRoutesRequest,
  enabled = true,
) =>
  useQuery({
    queryKey: packSubmissionKeys.routes(
      id,
      ref ?? { pack: "", template: "", version: "" },
      revision,
      body,
    ),
    queryFn: () =>
      packSubmissionApi.routes(
        id,
        ref ?? { pack: "", template: "", version: "" },
        body,
      ),
    enabled: ref !== null && enabled,
    placeholderData: (previous) => previous,
    retry: false,
  });
