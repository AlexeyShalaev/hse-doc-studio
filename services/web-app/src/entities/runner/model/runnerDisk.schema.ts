import type { ZodType } from "zod";
import { z } from "zod";

// Диск раннера: замер, очистка по целям и ход команды (docs/design/storage-cleanup.md, разделы 5 и 9.1).
// Бэкенда ещё нет (срезы B5 и B6): форма держится здесь, эталоны в ../testing/fixtures.ts.
// strictObject повторяет extra=forbid сервера: все поля приходят явно, пустое значение null,
// время ISO 8601 UTC, размеры в байтах целыми.

const iso = z.string().min(1);
const bytes = z.number().int().nonnegative();
const count = z.number().int().nonnegative();

/** Цели очистки (5.2). Сервер передаёт раннеру только их, никогда ссылки на образы (S1). */
export const DISK_TARGETS = [
  "old_versions",
  "unused_images",
  "build_cache",
  "dangling_images",
  "stopped_containers",
  "runner_cache",
] as const;
export const DiskTargetSchema = z.enum(DISK_TARGETS);
export type DiskTarget = z.infer<typeof DiskTargetSchema>;

/**
 * Категории полосы, порядок постоянный, как у локального «Диска»: образы сервисов Студии,
 * затем кэш сборки Docker (`cache`) и прочее своё (`runtime`: висячие слои, слои контейнеров, тома).
 */
export const DISK_CATEGORY_KEYS = [
  "compile",
  "languagetool",
  "office",
  "ai",
  "app",
  "cache",
  "runtime",
] as const;
export const DiskCategoryKeySchema = z.enum(DISK_CATEGORY_KEYS);
export type DiskCategoryKey = z.infer<typeof DiskCategoryKeySchema>;

/** Категории образов Студии: неиспользуемый образ всегда из них (не `other` и не висячий). */
export const DiskImageCategorySchema = z.enum([
  "compile",
  "languagetool",
  "office",
  "ai",
  "app",
]);
export type DiskImageCategory = z.infer<typeof DiskImageCategorySchema>;

export const DiskCategorySchema = z.strictObject({
  key: DiskCategoryKeySchema,
  bytes,
});
export type DiskCategory = z.infer<typeof DiskCategorySchema>;

/** Старая версия: образ Студии, образ сервиса или контейнер на нём (как OldVersions локального «Диска»). */
export const DiskOldItemSchema = z.strictObject({
  kind: z.enum(["studio_image", "service_image", "container"]),
  ref: z.string(),
  version: z.string(),
  size_bytes: bytes,
});
export type DiskOldItem = z.infer<typeof DiskOldItemSchema>;

export const DiskOldVersionsSchema = z.strictObject({
  /** Версия раннера: всё ниже неё считается старым. */
  current_version: z.string(),
  /** Предыдущая версия для отката: сохраняется, пока не попросили `include_rollback`. */
  rollback: DiskOldItemSchema.nullable(),
  items: z.array(DiskOldItemSchema).max(100),
  reclaimable_bytes: bytes,
  rollback_bytes: bytes,
});
export type DiskOldVersions = z.infer<typeof DiskOldVersionsSchema>;

export const DiskUnusedImageSchema = z.strictObject({
  ref: z.string(),
  category: DiskImageCategorySchema,
  size_bytes: bytes,
});
export type DiskUnusedImage = z.infer<typeof DiskUnusedImageSchema>;

/**
 * Docker-часть отчёта. `available: false`: docker не ответил, тогда числа 0, списки пусты,
 * `old_versions` без пунктов и с версией раннера.
 */
export const DockerDiskSchema = z.strictObject({
  available: z.boolean(),
  categories: z.array(DiskCategorySchema),
  total_bytes: bytes,
  cleanable_bytes: bytes,
  build_cache: z.strictObject({
    bytes,
    reclaimable_bytes: bytes,
    count,
  }),
  dangling: z.strictObject({ bytes, count }),
  stopped_containers: z.strictObject({ bytes, count }),
  unused_images: z.array(DiskUnusedImageSchema).max(100),
  unused_truncated: z.boolean(),
  old_versions: DiskOldVersionsSchema,
  volumes: z.array(z.strictObject({ name: z.string(), size_bytes: bytes })),
});
export type DockerDisk = z.infer<typeof DockerDiskSchema>;

export const RunnerCacheDiskSchema = z.strictObject({
  blobs: z.strictObject({ bytes, count, limit_bytes: bytes }),
  workspaces: z.strictObject({
    bytes,
    count,
    limit_bytes: bytes,
    /** Сколько рабочих копий сейчас под замком задачи: их очистка пропустит. */
    busy: count,
  }),
});
export type RunnerCacheDisk = z.infer<typeof RunnerCacheDiskSchema>;

/** Почему Docker-части нет: раннер в Kubernetes (S6) или это локальная Студия (S7). */
export const DockerDiskReasonSchema = z.enum(["kubernetes", "managed_locally"]);
export type DockerDiskReason = z.infer<typeof DockerDiskReasonSchema>;

/** Последний замер, присланный раннером (5.1, `core/jobs/disk.py`). */
export const RunnerDiskReportSchema = z.strictObject({
  measured_at: iso,
  /** Цели, которые раннер умеет выполнить сейчас; остальные сервер отвергает. */
  targets: z.array(DiskTargetSchema),
  docker: DockerDiskSchema.nullable(),
  docker_reason: DockerDiskReasonSchema.nullable(),
  cache: RunnerCacheDiskSchema,
  volume: z.strictObject({ total_bytes: bytes, free_bytes: bytes }).nullable(),
});
export type RunnerDiskReport = z.infer<typeof RunnerDiskReportSchema>;

// Команда раннеру и её ход (5.3).

export const RUNNER_DISK_COMMAND_STATES = [
  "queued",
  "delivered",
  "running",
  "cancelling",
  "done",
  "cancelled",
  "error",
  "expired",
  "lost",
] as const;
export const RunnerDiskCommandStateSchema = z.enum(RUNNER_DISK_COMMAND_STATES);
export type RunnerDiskCommandState = z.infer<
  typeof RunnerDiskCommandStateSchema
>;

export const RunnerDiskCommandKindSchema = z.enum([
  "disk.measure",
  "disk.cleanup",
]);
export type RunnerDiskCommandKind = z.infer<typeof RunnerDiskCommandKindSchema>;

/** Вид шага: первые четыре это шаги локального «Диска», два последних кэш раннера. */
export const DiskStepKindSchema = z.enum([
  "build_cache",
  "dangling_images",
  "image",
  "container",
  "runner_blobs",
  "runner_workspaces",
]);
export type DiskStepKind = z.infer<typeof DiskStepKindSchema>;

export const DiskStepStatusSchema = z.enum([
  "pending",
  "running",
  "done",
  "error",
  "skipped",
]);
export type DiskStepStatus = z.infer<typeof DiskStepStatusSchema>;

export const DiskStepSchema = z.strictObject({
  kind: DiskStepKindSchema,
  /** `repo:tag` или id висячего слоя у образа, имя у контейнера, null у остальных. */
  ref: z.string().nullable(),
  status: DiskStepStatusSchema,
  freed_bytes: bytes,
  /** Одна строка до 300 символов (последняя строка stderr Docker). */
  error: z.string().max(300).nullable(),
});
export type DiskStep = z.infer<typeof DiskStepSchema>;

export const CommandProgressSchema = z.strictObject({
  steps: z.array(DiskStepSchema),
  freed_bytes: bytes,
  error: z.string().nullable(),
});
export type CommandProgress = z.infer<typeof CommandProgressSchema>;

const PersonRefSchema = z.strictObject({ id: z.string(), name: z.string() });
export type PersonRef = z.infer<typeof PersonRefSchema>;

export const RunnerDiskCommandSchema = z.strictObject({
  id: z.string(),
  kind: RunnerDiskCommandKindSchema,
  state: RunnerDiskCommandStateSchema,
  /** Цели очистки; у `disk.measure` пусто. */
  targets: z.array(DiskTargetSchema),
  include_rollback: z.boolean(),
  created_at: iso,
  finished_at: iso.nullable(),
  /** Кто запустил; null, если человека уже нет в установке. */
  created_by: PersonRefSchema.nullable(),
  progress: CommandProgressSchema.nullable(),
});
export type RunnerDiskCommand = z.infer<typeof RunnerDiskCommandSchema>;

// Ответы админки и «Моих раннеров» (9.1).

/** Почему диска нет: раннер старой версии не согласовал `control` и `disk`. Отозванный раннер даёт 404. */
export const RunnerDiskUnsupportedReasonSchema = z.enum(["outdated"]);

export const RunnerDiskViewSchema = z.strictObject({
  runner_id: z.string(),
  supported: z.boolean(),
  reason: RunnerDiskUnsupportedReasonSchema.nullable(),
  /** С какой версии раннер сообщает о диске: экран берёт её отсюда, а не из кода. */
  min_version: z.string(),
  /** Раннер на связи сейчас (тот же критерий, что статус `offline` в списке, только наоборот). */
  online: z.boolean(),
  last_seen_at: iso.nullable(),
  report: RunnerDiskReportSchema.nullable(),
  /** Когда сервер принял замер; null, пока замера нет. */
  received_at: iso.nullable(),
  /** Замер старше суток. */
  stale: z.boolean(),
  /** Незавершённая очистка или последняя завершённая за 24 часа. */
  command: RunnerDiskCommandSchema.nullable(),
  /** Стоит или идёт `disk.measure`. */
  measuring: z.boolean(),
  can_clean: z.boolean(),
  can_include_rollback: z.boolean(),
  /** Владелец личного раннера: только в админке и только у личного раннера. */
  personal_owner: PersonRefSchema.nullable(),
});
export type RunnerDiskView = z.infer<typeof RunnerDiskViewSchema>;

export const RunnerDiskCleanupRequestSchema = z.strictObject({
  targets: z
    .array(DiskTargetSchema)
    .min(1)
    .max(DISK_TARGETS.length)
    .refine((targets) => new Set(targets).size === targets.length, {
      message: "targets must be unique",
    }),
  include_rollback: z.boolean(),
});
export type RunnerDiskCleanupRequest = z.infer<
  typeof RunnerDiskCleanupRequestSchema
>;

/** Сводка дисков общих раннеров для «Хранилища» (`GET /api/admin/runners/disk-summary`). */
export const RunnerDiskSummarySchema = z.strictObject({
  /** Сколько неотозванных общих раннеров прислали отчёт. */
  reporting: count,
  /** Сколько неотозванных общих раннеров не умеют сообщать о диске. */
  outdated: count,
  min_version: z.string(),
  cleanable_bytes: bytes,
  top: z
    .array(
      z.strictObject({
        runner_id: z.string(),
        name: z.string(),
        cleanable_bytes: bytes,
        measured_at: iso,
      }),
    )
    .max(3),
});
export type RunnerDiskSummary = z.infer<typeof RunnerDiskSummarySchema>;

/**
 * Поле `disk` строки списка раннеров (админка `RunnerInfo`, «Мои раннеры» `MyRunner`):
 * по нему меню решает, показывать «Диск» как обычно или с пометкой «обновите».
 */
export const RunnerDiskBriefSchema = z.strictObject({
  supported: z.boolean(),
  /** null, пока замера нет. */
  cleanable_bytes: bytes.nullable(),
  measured_at: iso.nullable(),
});
export type RunnerDiskBrief = z.infer<typeof RunnerDiskBriefSchema>;

/**
 * Схемы раздела 9.1 по именам будущих каталогов contracts/server/fixtures. Срез B6 перенесёт
 * эталоны в contracts/server/fixtures, модели в test_server_contract.py, а эту карту в
 * CONTRACT_SCHEMAS (entities/session/api/contractSchemas.ts); до тех пор каталогов нет, и
 * общий контрактный тест о диске не знает.
 */
export const RUNNER_DISK_CONTRACT_SCHEMAS: Record<string, ZodType> = {
  RunnerDiskView: RunnerDiskViewSchema,
  RunnerDiskCommand: RunnerDiskCommandSchema,
  RunnerDiskCleanupRequest: RunnerDiskCleanupRequestSchema,
  RunnerDiskSummary: RunnerDiskSummarySchema,
};
