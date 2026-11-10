import { z } from "zod";

export const SignModeSchema = z.enum([
  "image",
  "image_crypto",
  "crypto_invisible",
  "detached",
  "detached_text",
]);

export const SignerInfoSchema = z.object({
  kind: z.enum(["x509", "openpgp", "manual"]),
  owner: z.string(),
  cert_id: z.string(),
  valid_from: z.string().nullable(),
  valid_to: z.string().nullable(),
  signer_id: z.string(),
  level: z.string().optional().default(""),
});

export const SlotInfoSchema = z.object({
  png_path: z.string().nullable(),
  natural_width_px: z.number().nullable(),
  natural_height_px: z.number().nullable(),
  signing_identity_id: z.string().uuid().nullable().optional().default(null),
  sign_mode: SignModeSchema.optional().default("image"),
  sign_reason: z.string().optional().default(""),
  signer: SignerInfoSchema.nullish().default(null),
});

export const PlacementSchema = z.object({
  enabled: z.boolean(),
  page: z.number(),
  x_mm: z.number(),
  y_mm: z.number(),
  width_mm: z.number(),
  sign_date: z.string().nullable().optional().default(null),
});

// Контрольная точка, требующая подпись этого слота на конкретном документе.
export const SignatureProfileRefSchema = z.object({
  id: z.string(),
  name: z.record(z.string(), z.string()),
});

// Effective slot set computed by the backend for the CURRENT project. In team
// mode per-author slots are multiplied ("author--ivanov", label already carries
// the name) and applies_to/required_by reference document INSTANCE ids. When
// non-empty, the signatures UI must use these instead of the catalog slot defs
// (whose applies_to are pack definition ids and won't match instances).
export const RuntimeSignatureSlotSchema = z.object({
  id: z.string(),
  label: z.record(z.string(), z.string()),
  applies_to: z.array(z.string()),
  // Где подпись ОБЯЗАТЕЛЬНА и на какой точке: id документа → контрольные точки.
  // Пришло на смену `required_for: string[]`: обязательность зависит от точки
  // (ТЗ на КТ2 идёт без подписи научрука, на ГИА — обязательно с ней), и
  // отдельное поле у слота выразить это не могло.
  required_by: z
    .record(z.string(), z.array(SignatureProfileRefSchema))
    .default({}),
  default_placement: z.object({
    page: z.number(),
    x_mm: z.number(),
    y_mm: z.number(),
    width_mm: z.number(),
  }),
  owner: z.string().nullish().default(null),
});

export const DetachedVerdictSchema = z.enum([
  "valid",
  "invalid",
  "unverified",
  "unknown_key",
]);

export const FrozenPdfSchema = z.object({
  sha256: z.string(),
  size: z.number(),
  frozen_at: z.string(),
  stale: z.boolean(),
  plate_outdated: z.boolean().optional().default(false),
});

export const DetachedSignatureSchema = z.object({
  format: z.enum(["openpgp", "cms"]),
  origin: z.enum(["uploaded", "studio"]),
  verdict: DetachedVerdictSchema,
  signer: z.string(),
  signer_id: z.string(),
  issuer: z.string(),
  algorithm: z.string(),
  signed_at: z.string().nullable(),
  not_before: z.string().nullable(),
  not_after: z.string().nullable(),
  chain: z.string().nullable(),
  root_subject: z.string().optional().default(""),
  root_fingerprint: z.string().optional().default(""),
  notes: z.array(z.string()),
  added_at: z.string(),
  file_name: z.string(),
  current: z.boolean(),
});

export const FreezePdfResponseSchema = z.object({
  frozen: FrozenPdfSchema,
  dropped_slots: z.array(z.string()),
});

export const AttachDetachedResponseSchema = z.object({
  signature: DetachedSignatureSchema,
  missing_key_id: z.string().nullish().default(null),
});

export const SignaturesStateSchema = z.object({
  slots: z.record(z.string(), SlotInfoSchema),
  placements: z.record(z.string(), z.record(z.string(), PlacementSchema)),
  frozen: z.record(z.string(), FrozenPdfSchema).default({}),
  detached: z
    .record(z.string(), z.record(z.string(), DetachedSignatureSchema))
    .default({}),
  runtime_slots: z.array(RuntimeSignatureSlotSchema).default([]),
  /** Слоты документов, чью картинку придержал маршрут подписания до согласия подписанта. */
  withheld: z.record(z.string(), z.array(z.string())).default({}),
});

export const UploadSignatureResponseSchema = z.object({
  png_path: z.string(),
  natural_width_px: z.number().nullable(),
  natural_height_px: z.number().nullable(),
});

export const UpdatePlacementRequestSchema = z.object({
  enabled: z.boolean().optional(),
  page: z.number().optional(),
  x_mm: z.number().optional(),
  y_mm: z.number().optional(),
  width_mm: z.number().optional(),
  sign_date: z.string().optional(),
});

// План подписей (GET /projects/{id}/signature-plan): кто, каким способом, в
// каком статусе и чего не хватает. Счётчик точки сдачи считает по нему, а не по
// размещениям: открепленная ЭП без файла подписи — это «нет подписи», даже если
// плашка уже стоит на странице.
export const SignMethodSchema = z.enum(["image", "detached", "pades"]);
export const SlotStatusSchema = z.enum([
  "pending",
  "signed",
  "invalid",
  "stale",
]);

export const PlanSlotSchema = z.object({
  slot_id: z.string(),
  label: z.record(z.string(), z.string()),
  signer: z.object({ persona: z.string(), name: z.string() }),
  mode: SignModeSchema,
  method: SignMethodSchema,
  crypto: z.boolean(),
  mark: z.enum(["png", "plate", "none"]),
  status: SlotStatusSchema,
  reason: z.string().nullable().default(null),
  hint: z.string().default(""),
  allowed_methods: z.array(z.string()).default([]),
  required_by: z.array(z.string()).default([]),
  is_mine: z.boolean().default(false),
  check: z
    .object({
      format: z.string(),
      verdict: DetachedVerdictSchema,
      signer: z.string(),
      signer_id: z.string(),
      signed_at: z.string().nullable().default(null),
      notes: z.array(z.string()).default([]),
    })
    .nullable()
    .default(null),
  // Состояние участника маршрута подписания, чей это слот (signing-route.md, 6.1).
  route_state: z.string().nullable().default(null),
});

// Маршрут подписания, который держит документы точки сдачи или документ: состояние
// сервер считает на текущих файлах, поэтому остановка видна раньше, чем записана.
export const PlanRouteSchema = z.object({
  id: z.string(),
  profile_id: z.string(),
  status: z.string(),
  phase: z.string().nullable().default(null),
  round: z.number(),
  current_step: z.number().nullable().default(null),
  steps_total: z.number(),
  stop_reason: z.string().nullable().default(null),
  /** Документы маршрута, рабочая сборка которых ушла от версии на подписи (signing-route.md, 12.9). */
  changed_docs: z.array(z.string()).default([]),
});

// Версия на подписи (signing-route.md, 12.3): копия собранного PDF, которую снял маршрут при
// отправке. Пока она есть, план, фиксация и пакет берут её, а не текущую сборку. Остаётся после
// завершения маршрута, снимается при отмене и кнопкой «Подписывать текущую сборку».
export const PinnedPdfSchema = z.object({
  sha256: z.string(),
  pinned_at: z.string(),
  route_id: z.string(),
  round: z.number(),
});

export const DocPlanSchema = z.object({
  doc_id: z.string(),
  built: z.boolean(),
  frozen: z
    .object({
      sha256: z.string(),
      source_sha256: z.string(),
      frozen_at: z.string(),
      signed_sha256: z.string().default(""),
      outdated: z.string().nullable().default(null),
    })
    .nullable()
    .default(null),
  slots: z.array(PlanSlotSchema),
  /** Документ держит идущий маршрут подписания: фиксирует его только маршрут. */
  held_by_route: z.boolean().default(false),
  /** Версия на подписи; null, если документ подписывается по текущей сборке. */
  pinned: PinnedPdfSchema.nullable().default(null),
  /** Рабочая сборка есть и отличается от версии на подписи: «Есть изменения после отправки». */
  working_differs: z.boolean().default(false),
});

export const SignaturePlanSchema = z.object({
  profile_id: z.string().nullable().default(null),
  total: z.number(),
  signed: z.number(),
  crypto_total: z.number(),
  crypto_signed: z.number(),
  waiting_for_me: z.number().default(0),
  docs: z.array(DocPlanSchema),
  route: PlanRouteSchema.nullable().default(null),
});

// «Подписать комплект»: предпросмотр (что будет зафиксировано, чьи подписи
// сбросятся, какие свои слоты и чем подпишутся) и сама подпись.
export const SignPreviewSchema = z.object({
  profile_id: z.string(),
  key: z
    .object({
      id: z.string(),
      label: z.string(),
      kind: z.string(),
      protected: z.boolean(),
      auto: z.boolean(),
      signer: z.string(),
    })
    .nullable(),
  needs_passphrase: z.boolean(),
  to_sign: z.number(),
  docs: z.array(
    z.object({
      doc_id: z.string(),
      token: z.string(),
      needs_freeze: z.boolean(),
      can_freeze: z.boolean(),
      resets: z.array(
        z.object({
          slot_id: z.string(),
          label: z.record(z.string(), z.string()),
          signer: z.string(),
          method: z.string(),
        }),
      ),
      slots: z.array(
        z.object({
          slot_id: z.string(),
          label: z.record(z.string(), z.string()),
          method: SignMethodSchema,
          status: SlotStatusSchema,
          action: z.string(),
          blocker: z.string().default(""),
        }),
      ),
      blocker: z.string().default(""),
      // Документ держит идущий маршрут подписания: комплект его не фиксирует
      // (signing-route.md, 6.10), подписывают на странице `/sign/...`.
      route_id: z.string().nullable().default(null),
    }),
  ),
});

export const SignSubmissionResultSchema = z.object({
  frozen_docs: z.array(z.string()),
  results: z.array(
    z.object({
      doc_id: z.string(),
      slot_id: z.string(),
      ok: z.boolean(),
      message: z.string().default(""),
    }),
  ),
  plan: SignaturePlanSchema,
});
