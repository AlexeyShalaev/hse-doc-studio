import { z } from "zod";

// Вычислитель результата Студии шаблонов (docs/design/template-studio-outcome.md, раздел 4):
// по версии шаблона и вводным сервер считает результат и объясняет каждое решение цепочкой правил
// (`trace`). Клиент условий не считает, он показывает ответ сервера. Эталоны из
// contracts/pack-studio/fixtures разбирают и эти схемы (contract.test.ts), и строгие модели
// бэкенда (api/schemas/pack_studio_outcome.py). Эндпоинтов у схем пока нет: срез O1 плана.

const LocalizedSchema = z.record(z.string(), z.string());

/** Откуда считать: рабочее дерево, последний коммит ветки, вершина базовой ветки. */
export const OutcomeStateSchema = z.enum(["work_tree", "head", "base"]);

/** Разделы результата: колонки матрицы, строки сводки диффа, адресат правила. */
export const OutcomeSectionSchema = z.enum([
  "documents",
  "meta",
  "forms",
  "participants",
  "points",
  "route",
  "checks",
]);

const DocumentStateSchema = z.enum(["active", "inactive", "absent"]);
const ScopeSchema = z.enum(["shared", "personal"]);
const RoleSchema = z.enum([
  "author",
  "supervisor",
  "co_supervisor",
  "academic_supervisor",
]);
const OrgSchema = z.enum(["university", "company"]);
const OrderSourceSchema = z.enum(["profile", "version", "builtin"]);
const ItemOffReasonSchema = z.enum(["nda", "kind", "absent", "inactive"]);
const OutOfScopeSchema = z.enum([
  "python_checks",
  "signature_anchors",
  "tex_content",
  "jinja_content",
]);

export const OutcomeElementRefSchema = z.strictObject({
  section: OutcomeSectionSchema,
  id: z.string().min(1).max(2000),
});

// ── Правила и объяснения ─────────────────────────────────────────────────────

export const OutcomeRuleRefSchema = z
  .strictObject({
    origin: z.enum(["manifest", "builtin"]),
    file: z.string().nullable(),
    pointer: z.string().nullable(),
    builtin: z
      .enum([
        "nda_gate",
        "manuals_gate",
        "presentation_variant",
        "builtin_route",
      ])
      .nullable(),
  })
  .refine((rule) =>
    rule.origin === "manifest"
      ? rule.file !== null && rule.pointer !== null
      : rule.builtin !== null,
  );

export const OutcomeRuleKindSchema = z.enum([
  "supported_kinds",
  "supported_staffing",
  "supported_langs",
  "document_scope",
  "variant_langs",
  "builtin_gate",
  "field_kinds",
  "visible_if",
  "required_at",
  "form_kinds",
  "form_per_author",
  "item_kinds",
  "extra_kinds",
  "skip_if_nda",
  "item_document",
  "slot_when",
  "slot_optional",
  "route_order",
  "check_applies",
  "check_disabled",
]);

export const OutcomeTermSchema = z.strictObject({
  op: z.enum(["in", "equals", "contains_any", "present", "truthy"]),
  subject: z.string().min(1).max(128),
  expected: z.array(z.string()).max(32),
});

export const OutcomeTraceSchema = z.strictObject({
  id: z.string().min(1).max(32),
  rule: OutcomeRuleRefSchema,
  kind: OutcomeRuleKindSchema,
  effect: z.enum(["gate", "exclude", "add", "order", "display", "require"]),
  join: z.enum(["all", "any"]),
  terms: z.array(OutcomeTermSchema).max(8),
  // Что вычислитель увидел: вводная или факт и его значение.
  actual: z.record(z.string(), z.string()),
  // held: условие выполнено; not_held: нет; skipped: не проверялось, исход решён раньше.
  status: z.enum(["held", "not_held", "skipped"]),
  subjects: z.array(OutcomeElementRefSchema).max(64),
});

// ── Результат ────────────────────────────────────────────────────────────────

export const OutcomeVariantOptionSchema = z.strictObject({
  id: z.string(),
  label: LocalizedSchema,
  langs: z.array(z.string()),
  available: z.boolean(),
  chosen: z.boolean(),
  why: z.array(z.string()),
});

export const OutcomeInstanceSchema = z.strictObject({
  id: z.string(),
  owner: z.string().nullable(),
  owner_name: z.string().nullable(),
  file_name: z.string().nullable(),
});

export const OutcomeDocumentSchema = z.strictObject({
  id: z.string(),
  name: LocalizedSchema,
  group: z.string().nullable(),
  scope: ScopeSchema,
  required: z.boolean(),
  // active в комплекте; inactive в проекте, но выключен (NDA, руководства); absent в проекте нет.
  state: DocumentStateSchema,
  // fallback: у языка проекта нет редакции, берётся язык шаблона по умолчанию.
  lang_state: z.enum(["native", "fallback"]),
  languages: z.array(z.string()),
  variants: z.array(OutcomeVariantOptionSchema),
  instances: z.array(OutcomeInstanceSchema),
  source_file: z.string().nullable(),
  manifest: z.string(),
  why: z.array(z.string()),
});

export const OutcomeMetaFieldSchema = z.strictObject({
  id: z.string(),
  type: z.enum(["string", "bool", "person", "select", "font"]),
  label: LocalizedSchema,
  scope: z.enum(["project", "author"]),
  group: z.string().nullable(),
  visible: z.boolean(),
  required_at: z.enum(["create", "finalize", "never"]),
  value: z.string().nullable(),
  options: z.array(z.string()),
  why: z.array(z.string()),
});

export const OutcomeFormFieldSchema = z.strictObject({
  id: z.string(),
  type: z.string(),
  label: LocalizedSchema,
  visible: z.boolean(),
  required: z.boolean(),
  why: z.array(z.string()),
});

export const OutcomeFormSchema = z.strictObject({
  id: z.string(),
  title: LocalizedSchema,
  per_author: z.boolean(),
  applies: z.boolean(),
  required_for_pack: z.boolean(),
  fields: z.array(OutcomeFormFieldSchema),
  why: z.array(z.string()),
});

export const OutcomeParticipantSchema = z.strictObject({
  persona: z.string(),
  role: RoleSchema,
  name: z.string(),
  // Ложно у руководителя, которого нет в комбинации: слот остаётся виден бледным.
  present: z.boolean(),
  org: OrgSchema.nullable(),
  why: z.array(z.string()),
});

export const OutcomePointItemSchema = z.strictObject({
  doc_id: z.string(),
  active: z.boolean(),
  off_reason: ItemOffReasonSchema.nullable(),
  signatures: z.array(z.string()),
  why: z.array(z.string()),
});

export const OutcomePointExtraSchema = z.strictObject({
  source: z.string(),
  output_name: z.string(),
  format: z.string().nullable(),
  active: z.boolean(),
  off_reason: ItemOffReasonSchema.nullable(),
  why: z.array(z.string()),
});

const WhenSchema = z.strictObject({
  person: z.enum(["supervisor", "co_supervisor", "academic_supervisor"]),
  role: OrgSchema.nullable(),
});

export const OutcomeRoutePairSchema = z.strictObject({
  doc_id: z.string(),
  slot_id: z.string(),
  persona: z.string(),
  source: z.enum(["point", "preset"]),
  optional: z.boolean(),
  when: WhenSchema.nullable(),
  why: z.array(z.string()),
});

export const OutcomeSkippedPairSchema = z.strictObject({
  doc_id: z.string(),
  slot_id: z.string(),
  when: WhenSchema.nullable(),
  why: z.array(z.string()),
});

const RoutePersonSchema = z.strictObject({
  persona: z.string(),
  role: RoleSchema,
  name: z.string(),
});

export const OutcomeRouteSchema = z.strictObject({
  // Шаги людьми; пусто: подписи точке не нужны.
  steps: z.array(z.array(RoutePersonSchema)),
  pairs: z.array(OutcomeRoutePairSchema),
  skipped: z.array(OutcomeSkippedPairSchema),
  // Подписи, которые автор проекта включит сам.
  may_add: z.array(z.strictObject({ doc_id: z.string(), slot_id: z.string() })),
  order_source: OrderSourceSchema,
  preset: z.boolean(),
  why: z.array(z.string()),
});

export const OutcomePointSchema = z.strictObject({
  id: z.string(),
  // Индекс профиля в списке YAML.
  index: z.number().int(),
  name: LocalizedSchema,
  deadline_hint: LocalizedSchema.nullable(),
  items: z.array(OutcomePointItemSchema),
  extra_items: z.array(OutcomePointExtraSchema),
  route: OutcomeRouteSchema,
  why: z.array(z.string()),
});

export const OutcomeCheckRuleSchema = z.strictObject({
  id: z.string(),
  title: LocalizedSchema,
  category: z.string().nullable(),
  severity: z.enum(["info", "warn", "err"]),
  engine: z.string(),
  enabled: z.boolean(),
  off_reason: z
    .enum(["disabled", "category_disabled", "no_active_document"])
    .nullable(),
  applies_to: z.array(z.string()),
  why: z.array(z.string()),
});

export const OutcomeSectionDeltaSchema = z.strictObject({
  section: OutcomeSectionSchema,
  added: z.number().int().min(0),
  changed: z.number().int().min(0),
  removed: z.number().int().min(0),
});

export const OutcomeAlternativeSchema = z.strictObject({
  value: z.string(),
  label: LocalizedSchema.nullable(),
  fingerprint: z.string(),
  // Что изменится, если выбрать это значение; пусто у текущего.
  delta: z.array(OutcomeSectionDeltaSchema),
});

export const OutcomeBranchSchema = z.strictObject({
  input: z.string(),
  label: LocalizedSchema.nullable(),
  chosen: z.string(),
  affects: z.array(OutcomeSectionSchema),
  alternatives: z.array(OutcomeAlternativeSchema),
});

export const OutcomeSectionPrintSchema = z.strictObject({
  section: OutcomeSectionSchema,
  fingerprint: z.string(),
  count: z.number().int().min(0),
});

export const OutcomeDigestPointSchema = z.strictObject({
  id: z.string(),
  items: z.array(z.string()),
  steps: z.array(z.array(z.string())),
  pairs: z.number().int().min(0),
});

/** Сжатый результат: перерисовка из атласа, сравнение сценариев, снимок в сценарии. */
export const OutcomeDigestSchema = z.strictObject({
  documents: z.record(z.string(), DocumentStateSchema),
  participants: z.array(z.string()),
  meta_visible: z.array(z.string()),
  points: z.array(OutcomeDigestPointSchema),
  sections: z.array(OutcomeSectionPrintSchema),
});

// ── Запрос и ответ вычислителя ───────────────────────────────────────────────

const InputsSchema = z.record(z.string(), z.string());

export const PackOutcomeRequestSchema = z.strictObject({
  state: OutcomeStateSchema.optional(),
  scenario: z.string().max(128).nullish(),
  example: z.string().max(255).nullish(),
  inputs: InputsSchema.optional(),
  // Дорогие части ответа: ветки (что-если по каждой вводной) и правила проверок.
  include: z
    .array(z.enum(["branches", "checks"]))
    .max(2)
    .optional(),
});

export const PackOutcomeSchema = z.strictObject({
  workspace_id: z.string(),
  pack: z.string(),
  template: z.string(),
  version: z.string(),
  state: OutcomeStateSchema,
  // Дайджест манифестов, по которым считали: кэш и устаревание ответа.
  revision: z.string(),
  inputs: InputsSchema,
  example: z.string(),
  // Отпечаток структуры результата без `trace`.
  fingerprint: z.string(),
  documents: z.array(OutcomeDocumentSchema),
  meta: z.array(OutcomeMetaFieldSchema),
  forms: z.array(OutcomeFormSchema),
  participants: z.array(OutcomeParticipantSchema),
  points: z.array(OutcomePointSchema),
  checks: z.array(OutcomeCheckRuleSchema).nullable(),
  branches: z.array(OutcomeBranchSchema).nullable(),
  digest: OutcomeDigestSchema,
  trace: z.array(OutcomeTraceSchema),
  out_of_scope: z.array(OutOfScopeSchema),
  elapsed_ms: z.number().int().min(0),
});

// ── Вводные версии ───────────────────────────────────────────────────────────

export const OutcomeInputSchema = z.strictObject({
  id: z.string(),
  group: z.enum(["project", "people", "meta", "answers", "variants"]),
  type: z.enum(["select", "bool"]),
  label: LocalizedSchema.nullable(),
  values: z.array(
    z.strictObject({ value: z.string(), label: LocalizedSchema.nullable() }),
  ),
  default: z.string(),
  // Разделы, которые меняются при смене вводной, и число правил манифеста, которые её читают.
  affects: z.array(OutcomeSectionSchema),
  rules: z.number().int().min(0),
});

const PreviewExampleSchema = z.strictObject({
  id: z.string(),
  source: z.enum(["file", "auto"]),
  label: LocalizedSchema.nullable(),
  error: z.string().nullable(),
  defaults: z.record(z.string(), z.string()),
});

export const PackOutcomeInputsSchema = z.strictObject({
  workspace_id: z.string(),
  pack: z.string(),
  template: z.string(),
  version: z.string(),
  state: OutcomeStateSchema,
  revision: z.string(),
  inputs: z.array(OutcomeInputSchema),
  examples: z.array(PreviewExampleSchema),
  default_example: z.string(),
  defaults: z.record(z.string(), z.string()),
});

// ── Атлас ────────────────────────────────────────────────────────────────────

export const AtlasDimensionSchema = z.strictObject({
  input: z.string(),
  values: z.array(z.string()),
  default: z.string(),
  affects: z.array(OutcomeSectionSchema),
  rules: z.array(OutcomeRuleRefSchema).max(32),
});

export const AtlasIgnoredSchema = z.strictObject({
  input: z.string(),
  // no_effect: ничего не меняет; cosmetic: только имена файлов, варианты и языковая редакция.
  reason: z.enum(["no_effect", "cosmetic"]),
});

export const AtlasOutcomeSchema = z.strictObject({
  id: z.string(),
  fingerprint: z.string(),
  digest: OutcomeDigestSchema,
  rows: z.number().int().min(1),
});

/** `key`: значения измерений по порядку `dimensions` через `|` (в значении `|` пишется `%7C`). */
export const AtlasRowSchema = z.strictObject({
  key: z.string(),
  outcome: z.string(),
});

export const PackOutcomeAtlasSchema = z.strictObject({
  workspace_id: z.string(),
  pack: z.string(),
  template: z.string(),
  version: z.string(),
  state: OutcomeStateSchema,
  revision: z.string(),
  dimensions: z.array(AtlasDimensionSchema),
  ignored: z.array(AtlasIgnoredSchema),
  combinations_total: z.number().int().min(1),
  rows_total: z.number().int().min(1),
  outcomes_distinct: z.number().int().min(1),
  outcomes: z.array(AtlasOutcomeSchema),
  rows: z.array(AtlasRowSchema),
  elapsed_ms: z.number().int().min(0),
});

// ── Сценарии ─────────────────────────────────────────────────────────────────

const id128 = z.string().min(1).max(128);

export const ScenarioAssertionSchema = z.discriminatedUnion("kind", [
  z.strictObject({
    kind: z.literal("document_state"),
    doc: id128,
    state: DocumentStateSchema,
  }),
  z.strictObject({
    kind: z.literal("document_count"),
    state: DocumentStateSchema,
    count: z.number().int().min(0).max(1000),
  }),
  z.strictObject({
    kind: z.literal("meta_visible"),
    field: id128,
    visible: z.boolean(),
  }),
  z.strictObject({
    kind: z.literal("participant_present"),
    persona: id128,
    present: z.boolean(),
  }),
  z.strictObject({
    kind: z.literal("item_active"),
    point: id128,
    doc: id128,
    active: z.boolean(),
  }),
  z.strictObject({
    kind: z.literal("route_steps"),
    point: id128,
    // Персоны по шагам; внутри шага порядок не важен.
    steps: z.array(z.array(z.string())).max(16),
  }),
  z.strictObject({
    kind: z.literal("route_pair"),
    point: id128,
    doc: id128,
    slot: id128,
    persona: id128,
    present: z.boolean(),
  }),
]);

/** Файл сценария `<пак>/templates/<шаблон>/scenarios/<id>.yaml` (рядом с `examples/`). */
export const PackScenarioSchema = z.strictObject({
  format: z.literal(1),
  name: LocalizedSchema.refine((v) => Object.keys(v).length > 0),
  description: LocalizedSchema.optional(),
  example: z.string().max(255).nullish(),
  inputs: InputsSchema,
  // Шаблоны номеров (`2026.1.*`); пусто: сценарий проверяется на любой версии.
  versions: z.array(z.string()).max(16).optional(),
  snapshot: OutcomeDigestSchema.nullish(),
  assertions: z.array(ScenarioAssertionSchema).max(64).optional(),
});

export const PackScenarioEntrySchema = z.strictObject({
  id: z.string(),
  path: z.string(),
  etag: z.string(),
  // null у файла, который не разобран (`error` почему).
  scenario: PackScenarioSchema.nullable(),
  error: z.string().nullable(),
});

export const PackScenarioListSchema = z.strictObject({
  workspace_id: z.string(),
  pack: z.string(),
  template: z.string(),
  dir: z.string(),
  scenarios: z.array(PackScenarioEntrySchema),
});

export const PackScenarioWriteRequestSchema = z.strictObject({
  scenario: PackScenarioSchema,
  // Заменить `snapshot` текущим результатом сценария на выбранном состоянии.
  record_snapshot: OutcomeStateSchema.nullish(),
  // Версия, на которой считается снимок; null: старшая версия шаблона, подходящая под `versions` сценария.
  version: z.string().max(128).nullish(),
});

export const PackScenarioRunRequestSchema = z.strictObject({
  state: OutcomeStateSchema.optional(),
  // null: все сценарии шаблона.
  scenarios: z.array(z.string()).max(200).nullish(),
  // Версия прогона; null: старшая версия шаблона на диске.
  version: z.string().max(128).nullish(),
});

// ── Покрытие и находки линтера результата ────────────────────────────────────

export const RuleCoverageSchema = z.strictObject({
  rule: OutcomeRuleRefSchema,
  kind: OutcomeRuleKindSchema,
  // Какие исходы правила видели сценарии; покрыто полностью, когда видели оба.
  seen: z.array(z.enum(["held", "not_held"])),
  scenarios: z.array(z.string()),
});

export const OutcomeCoverageSchema = z.strictObject({
  scenarios: z.number().int().min(0),
  rules_total: z.number().int().min(0),
  rules_covered: z.number().int().min(0),
  rules_half: z.number().int().min(0),
  rules_uncovered: z.number().int().min(0),
  // Только правила, покрытые не полностью.
  rules: z.array(RuleCoverageSchema),
});

export const OutcomeFindingSchema = z.strictObject({
  rule_id: z.string().min(1).max(64),
  severity: z.enum(["error", "warning", "info"]),
  message: z.string(),
  file: z.string().nullable(),
  pointer: z.string().nullable(),
  line: z.number().int().nullable(),
  elements: z.array(OutcomeElementRefSchema).max(16),
  // До трёх вводных, на которых находка видна.
  witnesses: z.array(InputsSchema).max(3),
});

export const PackOutcomeLintSchema = z.strictObject({
  workspace_id: z.string(),
  pack: z.string(),
  template: z.string(),
  version: z.string(),
  state: OutcomeStateSchema,
  revision: z.string(),
  errors: z.number().int().min(0),
  warnings: z.number().int().min(0),
  findings: z.array(OutcomeFindingSchema),
  coverage: OutcomeCoverageSchema,
});

// ── Изменения, прогон сценариев, сравнения, матрица ──────────────────────────

/** `+` появилось, `~` изменилось, `-` исчезло. */
export const OutcomeChangeSchema = z.strictObject({
  symbol: z.enum(["+", "~", "-"]),
  section: OutcomeSectionSchema,
  kind: z.enum([
    "document",
    "variant",
    "meta_field",
    "form",
    "form_field",
    "participant",
    "point",
    "item",
    "extra_item",
    "route_step",
    "route_pair",
    "skipped_pair",
    "check_rule",
  ]),
  id: z.string().min(1).max(2000),
  label: z.string().max(2000),
  before: z.string().nullable(),
  after: z.string().nullable(),
});

export const ScenarioFailureSchema = z.strictObject({
  // Индекс утверждения; null: расхождение со снимком.
  index: z.number().int().nullable(),
  kind: z.string(),
  expected: z.string(),
  actual: z.string(),
  why: z.array(z.string()),
});

export const PackScenarioRunResultSchema = z.strictObject({
  scenario: z.string(),
  // unchecked: ни снимка, ни утверждений; error: вводные не подходят к версии.
  status: z.enum(["passed", "failed", "error", "unchecked"]),
  fingerprint: z.string().nullable(),
  failures: z.array(ScenarioFailureSchema),
  changes: z.array(OutcomeChangeSchema),
  message: z.string().nullable(),
});

export const PackScenarioRunSchema = z.strictObject({
  workspace_id: z.string(),
  pack: z.string(),
  template: z.string(),
  version: z.string(),
  state: OutcomeStateSchema,
  revision: z.string(),
  passed: z.number().int().min(0),
  failed: z.number().int().min(0),
  errors: z.number().int().min(0),
  unchecked: z.number().int().min(0),
  results: z.array(PackScenarioRunResultSchema),
  coverage: OutcomeCoverageSchema,
});

/** Одна сторона сравнения: сценарий и (или) вводные на выбранном состоянии версии. */
export const OutcomeSubjectSchema = z.strictObject({
  state: OutcomeStateSchema.optional(),
  scenario: z.string().max(128).nullish(),
  example: z.string().max(255).nullish(),
  inputs: InputsSchema.optional(),
});

export const OutcomeSideSchema = z.strictObject({
  state: OutcomeStateSchema,
  revision: z.string(),
  fingerprint: z.string(),
  inputs: InputsSchema,
});

export const PackOutcomeCompareRequestSchema = z.strictObject({
  left: OutcomeSubjectSchema,
  right: OutcomeSubjectSchema,
});

export const PackOutcomeCompareSchema = z.strictObject({
  workspace_id: z.string(),
  pack: z.string(),
  template: z.string(),
  version: z.string(),
  left: OutcomeSideSchema,
  right: OutcomeSideSchema,
  identical: z.boolean(),
  summary: z.array(OutcomeSectionDeltaSchema),
  changes: z.array(OutcomeChangeSchema),
});

export const PackOutcomeImpactRequestSchema = z.strictObject({
  // base: вершина базовой ветки; head: последний коммит ветки.
  base: z.enum(["base", "head"]).optional(),
  scenarios: z.array(z.string()).max(200).nullish(),
  include_atlas: z.boolean().optional(),
});

export const ImpactScenarioSchema = z.strictObject({
  scenario: z.string(),
  name: LocalizedSchema,
  status: z.enum(["unchanged", "changed", "error"]),
  changes: z.array(OutcomeChangeSchema),
  message: z.string().nullable(),
});

export const ImpactSummarySchema = z.strictObject({
  scenarios_total: z.number().int().min(0),
  scenarios_changed: z.number().int().min(0),
  scenarios_unchanged: z.number().int().min(0),
  scenarios_error: z.number().int().min(0),
  sections: z.array(OutcomeSectionDeltaSchema),
  atlas: z
    .strictObject({
      rows_total: z.number().int().min(0),
      rows_changed: z.number().int().min(0),
      outcomes_before: z.number().int().min(0),
      outcomes_after: z.number().int().min(0),
    })
    .nullable(),
});

export const PackOutcomeImpactSchema = z.strictObject({
  workspace_id: z.string(),
  pack: z.string(),
  template: z.string(),
  version: z.string(),
  base: z.enum(["base", "head"]),
  base_revision: z.string(),
  work_tree_revision: z.string(),
  summary: ImpactSummarySchema,
  scenarios: z.array(ImpactScenarioSchema),
  // Находки линтера результата, которых на базе не было.
  new_findings: z.array(OutcomeFindingSchema),
});

export const PackOutcomeMatrixRequestSchema = z.strictObject({
  state: OutcomeStateSchema.optional(),
  scenarios: z.array(z.string()).max(200).nullish(),
  // base: у каждой клетки пометка, изменилась ли она против вершины базовой ветки.
  against: z.literal("base").nullish(),
});

export const MatrixCellSchema = z.strictObject({
  section: OutcomeSectionSchema,
  fingerprint: z.string(),
  count: z.number().int().min(0),
  // null: сравнения с базой не просили или сценария на базе нет.
  changed: z.boolean().nullable(),
});

export const MatrixRowSchema = z.strictObject({
  scenario: z.string(),
  name: LocalizedSchema,
  inputs: InputsSchema,
  cells: z.array(MatrixCellSchema),
});

export const PackOutcomeMatrixSchema = z.strictObject({
  workspace_id: z.string(),
  pack: z.string(),
  template: z.string(),
  version: z.string(),
  state: OutcomeStateSchema,
  revision: z.string(),
  columns: z.array(OutcomeSectionSchema),
  rows: z.array(MatrixRowSchema),
});

// ── «Почему?» ────────────────────────────────────────────────────────────────

export const PackOutcomeExplainRequestSchema = z.strictObject({
  state: OutcomeStateSchema.optional(),
  scenario: z.string().max(128).nullish(),
  example: z.string().max(255).nullish(),
  inputs: InputsSchema.optional(),
  element: OutcomeElementRefSchema,
});

export const OutcomeCounterfactualSchema = z.strictObject({
  input: z.string(),
  value: z.string(),
  // Состояние элемента при этом: у документа active, inactive или absent, у остальных present или absent.
  result: z.string(),
});

export const PackOutcomeExplainSchema = z.strictObject({
  element: OutcomeElementRefSchema,
  state: z.string(),
  // Цепочка решений от первого правила к последнему.
  chain: z.array(OutcomeTraceSchema),
  // Другие элементы, на которые влияют те же правила.
  readers: z.array(OutcomeElementRefSchema).max(64),
  counterfactuals: z.array(OutcomeCounterfactualSchema).max(32),
});

export type OutcomeState = z.infer<typeof OutcomeStateSchema>;
export type OutcomeSection = z.infer<typeof OutcomeSectionSchema>;
export type OutcomeElementRef = z.infer<typeof OutcomeElementRefSchema>;
export type OutcomeRuleRef = z.infer<typeof OutcomeRuleRefSchema>;
export type OutcomeTerm = z.infer<typeof OutcomeTermSchema>;
export type OutcomeTrace = z.infer<typeof OutcomeTraceSchema>;
export type OutcomeDocument = z.infer<typeof OutcomeDocumentSchema>;
export type OutcomeMetaField = z.infer<typeof OutcomeMetaFieldSchema>;
export type OutcomeForm = z.infer<typeof OutcomeFormSchema>;
export type OutcomeParticipant = z.infer<typeof OutcomeParticipantSchema>;
export type OutcomePoint = z.infer<typeof OutcomePointSchema>;
export type OutcomeRoute = z.infer<typeof OutcomeRouteSchema>;
export type OutcomeCheckRule = z.infer<typeof OutcomeCheckRuleSchema>;
export type OutcomeBranch = z.infer<typeof OutcomeBranchSchema>;
export type OutcomeDigest = z.infer<typeof OutcomeDigestSchema>;
export type PackOutcomeRequest = z.infer<typeof PackOutcomeRequestSchema>;
export type PackOutcome = z.infer<typeof PackOutcomeSchema>;
export type OutcomeInput = z.infer<typeof OutcomeInputSchema>;
export type PackOutcomeInputs = z.infer<typeof PackOutcomeInputsSchema>;
export type PackOutcomeAtlas = z.infer<typeof PackOutcomeAtlasSchema>;
export type ScenarioAssertion = z.infer<typeof ScenarioAssertionSchema>;
export type PackScenario = z.infer<typeof PackScenarioSchema>;
export type PackScenarioEntry = z.infer<typeof PackScenarioEntrySchema>;
export type PackScenarioList = z.infer<typeof PackScenarioListSchema>;
export type PackScenarioWriteRequest = z.infer<
  typeof PackScenarioWriteRequestSchema
>;
export type PackScenarioRunRequest = z.infer<
  typeof PackScenarioRunRequestSchema
>;
export type PackScenarioRun = z.infer<typeof PackScenarioRunSchema>;
export type OutcomeCoverage = z.infer<typeof OutcomeCoverageSchema>;
export type OutcomeFinding = z.infer<typeof OutcomeFindingSchema>;
export type PackOutcomeLint = z.infer<typeof PackOutcomeLintSchema>;
export type OutcomeChange = z.infer<typeof OutcomeChangeSchema>;
export type OutcomeSubject = z.infer<typeof OutcomeSubjectSchema>;
export type PackOutcomeCompareRequest = z.infer<
  typeof PackOutcomeCompareRequestSchema
>;
export type PackOutcomeCompare = z.infer<typeof PackOutcomeCompareSchema>;
export type PackOutcomeImpactRequest = z.infer<
  typeof PackOutcomeImpactRequestSchema
>;
export type PackOutcomeImpact = z.infer<typeof PackOutcomeImpactSchema>;
export type PackOutcomeMatrixRequest = z.infer<
  typeof PackOutcomeMatrixRequestSchema
>;
export type PackOutcomeMatrix = z.infer<typeof PackOutcomeMatrixSchema>;
export type PackOutcomeExplainRequest = z.infer<
  typeof PackOutcomeExplainRequestSchema
>;
export type PackOutcomeExplain = z.infer<typeof PackOutcomeExplainSchema>;
