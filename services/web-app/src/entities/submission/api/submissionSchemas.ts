import { z } from "zod";

const LocalizedStringSchema = z.record(z.string(), z.string());
const iso = z.string().min(1);

/**
 * Состояние срока контрольной точки (docs/design/signing-route.md, 16.6): считает сервер, чтобы
 * точка, список проектов и MCP говорили одно. Дни по календарю Москвы.
 */
export const DEADLINE_STATES = [
  "none",
  "upcoming",
  "soon",
  "today",
  "packaged",
  "overdue",
] as const;
export const DeadlineStateSchema = z.enum(DEADLINE_STATES);
export type DeadlineState = z.infer<typeof DeadlineStateSchema>;

/** Ответ `PUT .../submissions/profiles/{profile_id}/deadline` (16.8). */
export const CheckpointDeadlineSchema = z.strictObject({
  profile_id: z.string(),
  deadline: iso.nullable(),
  state: DeadlineStateSchema,
  /** Последняя сборка пакета точки к сроку: за 14 дней до срока и не позже него. */
  packaged_at: iso.nullable(),
});
export type CheckpointDeadline = z.infer<typeof CheckpointDeadlineSchema>;

/** Тело `PUT .../deadline`: момент с поясом (ISO 8601) или null, чтобы снять срок. */
export const SetCheckpointDeadlineRequestSchema = z.strictObject({
  deadline: iso.nullable(),
});
export type SetCheckpointDeadlineRequest = z.infer<
  typeof SetCheckpointDeadlineRequestSchema
>;

const SubmissionDocItemSchema = z.object({
  doc_id: z.string(),
  signatures: z.array(z.string()),
  // Гейты состава, которые применяет бэкенд в build_item_list. Сам
  // ДОКУМЕНТ может быть в проекте, а в комплект точки не входить: thesis
  // на КТ2 ВКР — только проектный формат, Текст программы не сдаётся под
  // NDA. Без них клиент показал бы блокер, которого при сборке не будет.
  skip_if_nda: z.boolean().default(false),
  supported_kinds: z.array(z.string()).default(["research", "project"]),
  // Допустимые способы подписи по слоту каталога; слота нет, значит любой способ.
  methods: z.record(z.string(), z.array(z.string())).default({}),
});

const SubmissionExtraItemSchema = z.object({
  source: z.string(),
  output_name: z.string(),
  format: z.string().nullish(),
  // Тот же гейт, что у пунктов-документов: «Ссылка на код.txt» на КТ2
  // входит в пакет только у исследовательского формата.
  supported_kinds: z.array(z.string()).default(["research", "project"]),
});

/**
 * Срок точки в проекте (16.8): момент, состояние, подсказка пака текстом без дат и последняя
 * сборка пакета к сроку. Сервер до R28 полей не присылал: тогда срока нет.
 */
const deadlineFields = {
  deadline: iso.nullable().default(null),
  deadline_state: DeadlineStateSchema.default("none"),
  deadline_hint: LocalizedStringSchema.nullable().default(null),
  packaged_at: iso.nullable().default(null),
};

export const SubmissionProfileSchema = z.object({
  id: z.string(),
  name: LocalizedStringSchema,
  description: LocalizedStringSchema,
  // Backend may omit these or return them empty depending on the endpoint;
  // .nullish() tolerates both null and undefined.
  items: z.array(SubmissionDocItemSchema).nullish(),
  extra_items: z.array(SubmissionExtraItemSchema).nullish(),
  ...deadlineFields,
});

/**
 * Профиль сдачи в контракте сервера (`SubmissionProfileResponse`, 16.8): строгая форма для
 * эталонов, лишнее поле верхнего уровня отвергается. Экраны разбирают терпимой схемой выше.
 */
export const SubmissionProfileContractSchema = z.strictObject({
  id: z.string(),
  name: LocalizedStringSchema,
  description: LocalizedStringSchema,
  items: z.array(SubmissionDocItemSchema),
  extra_items: z.array(SubmissionExtraItemSchema),
  deadline: iso.nullable(),
  deadline_state: DeadlineStateSchema,
  deadline_hint: LocalizedStringSchema.nullable(),
  packaged_at: iso.nullable(),
});

/**
 * Предупреждение пакета без пропуска файла. `changed_after_sent` (signing-route.md, 12.8): рабочая
 * сборка документа ушла от версии на подписи, в пакет попала подписанная версия от `sent_at`.
 */
export const PackWarningSchema = z.object({
  code: z.string(),
  doc_id: z.string().nullable().default(null),
  /** Слот у `optional_unsigned` (13.11), у остальных null. */
  slot_id: z.string().nullable().default(null),
  /** Дата версии на подписи у `changed_after_sent`, у остальных null. */
  sent_at: z.string().nullable().default(null),
  // Сверх контракта W7 (срез R14): имя файла в пакете, готовый текст на языке интерфейса,
  // версия на подписи той же формы, что `DocPlan.pinned` (по `route_id` интерфейс находит
  // маршрут для «Отправить новую версию»), и sha256 рабочей сборки.
  file: z.string().nullable().default(null),
  message: z.string().default(""),
  pinned: z
    .object({
      sha256: z.string(),
      pinned_at: z.string(),
      route_id: z.string(),
      round: z.number(),
    })
    .nullable()
    .default(null),
  working_sha256: z.string().nullable().default(null),
});
export type PackWarning = z.infer<typeof PackWarningSchema>;

export const SubmissionRecordSchema = z.object({
  id: z.string(),
  profile_id: z.string().nullish(),
  profile_name: z.record(z.string(), z.string()).nullish(),
  created_at: z.string(),
  output_path: z.string().nullable().optional(),
  output_dir: z.string().nullable().optional(),
  size_bytes: z.number().nullable().optional(),
  archive_format: z.string().nullish(),
  doc_count: z.number().nullish(),
  // Предупреждения плана пакета: только в ответе на создание, в списке пусто.
  warnings: z.array(PackWarningSchema).default([]),
});

export const CreateSubmissionRequestSchema = z.object({
  profile_id: z.string(),
  items: z.array(
    z.object({
      doc_id: z.string(),
      signatures: z.array(z.string()),
    }),
  ),
  extra_items: z
    .array(
      z.object({
        source: z.string(),
        output_name: z.string(),
        format: z.string().nullish(),
        // Тот же гейт, что у пунктов-документов: «Ссылка на код.txt» на КТ2
        // входит в пакет только у исследовательского формата.
        supported_kinds: z.array(z.string()).default(["research", "project"]),
      }),
    )
    .optional(),
  archive_format: z.enum(["zip", "targz", "7z", "rar"]).optional(),
  // REQUIRED for team projects: whose submission package is being built (their
  // personal docs + shared docs + their declaration).
  author_slug: z.string().optional(),
  // doc_id -> convert-to-pdf yes/no, for custom (non-template) documents in
  // this package. Empty/omitted when the package has no custom docs, or the
  // user didn't need to be asked (all custom docs already PDF).
  custom_doc_decisions: z.record(z.string(), z.boolean()).optional(),
});

export const CustomFilePreflightItemSchema = z.object({
  doc_id: z.string(),
  doc_name: z.record(z.string(), z.string()),
  original_filename: z.string(),
  ext: z.string(),
  convertible: z.boolean(),
  default_decision: z.boolean().nullable().optional(),
});

// Backend returns a plain JSON array (response_model=list[...]), not a
// wrapped `{items: [...]}` envelope.
export const CustomFilePreflightResponseSchema = z.array(
  CustomFilePreflightItemSchema,
);
