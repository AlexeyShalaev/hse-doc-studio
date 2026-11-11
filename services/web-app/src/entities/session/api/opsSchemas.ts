import { z } from "zod";

import { RunnerDiskBriefSchema } from "@entities/runner/model/runnerDisk.schema";

import { pageOf } from "./schemas";

// Операционные экраны админки. Раннеры и токены разбираются схемами ниже (api/schemas/runner_admin.py).
// Очередь, квоты, сервисы и место приходят в формах api/schemas/admin_ops.py (схемы в schemas.ts),
// а экранам отдаются в видах ниже: имена вместо идентификаторов там, где сервер их не знает.

const iso = z.string().min(1);

export const RunnerStatusSchema = z.enum([
  "online",
  "stale",
  "offline",
  "paused",
  "revoked",
  "disabled",
]);
export const AdminRunnerSchema = z.strictObject({
  id: z.string(),
  name: z.string(),
  status: RunnerStatusSchema,
  tags: z.array(z.string()),
  concurrency: z.number().int(),
  resource_class: z.string(),
  version: z.string(),
  created_at: iso,
  last_seen_at: iso.nullable(),
  paused: z.boolean(),
  revoked: z.boolean(),
  owner_kind: z.enum(["instance", "user"]),
  owner: z
    .strictObject({ id: z.string(), name: z.string(), email: z.string() })
    .nullable(),
  host_kind: z.enum(["cli", "desktop"]),
  ai_endpoints: z.array(z.string()),
  last_seen_ip: z.string().nullable(),
  /** Почему раннер стоит переустановить, чтобы применились лимиты (по версии и отчёту). */
  reinstall: z.array(z.enum(["before_limits", "no_pod_limits"])).optional(),
  deployment_reported: z.boolean().optional(),
  /** Диск раннера кратко (storage-cleanup.md, 9.1); необязательно, пока сервер (B6) поля не шлёт. */
  disk: RunnerDiskBriefSchema.nullable().optional(),
});

// Как раннер развёрнут и как изолированы раннеры в кластере (api/schemas/runner_isolation.py).
const ResourcesViewSchema = z.strictObject({
  cpu_request: z.string().nullable(),
  cpu_limit: z.string().nullable(),
  memory_request: z.string().nullable(),
  memory_limit: z.string().nullable(),
  ephemeral_request: z.string().nullable(),
  ephemeral_limit: z.string().nullable(),
  source: z.enum(["pod", "cgroup", "config", "cluster"]),
});
const SecurityViewSchema = z.strictObject({
  run_as_non_root: z.boolean().nullable(),
  run_as_user: z.number().int().nullable(),
  read_only_root: z.boolean().nullable(),
  no_privilege_escalation: z.boolean().nullable(),
  seccomp: z.boolean().nullable(),
  capabilities_dropped: z.boolean().nullable(),
  automount_token: z.boolean().nullable(),
});
const BuildIsolationViewSchema = z.strictObject({
  namespace: z.string().nullable(),
  image: z.string().nullable(),
  resources: ResourcesViewSchema.nullable(),
  network_disabled: z.boolean().nullable(),
  pids_limit: z.number().int().nullable(),
  work_size_limit: z.string().nullable(),
  tmp_size_limit: z.string().nullable(),
  active_deadline_s: z.number().int().nullable(),
  runtime_class: z.string().nullable(),
  security: SecurityViewSchema.nullable(),
});
export const ReinstallReasonSchema = z.enum(["before_limits", "no_pod_limits"]);
export const AdminRunnerDeploymentSchema = z.strictObject({
  runner_id: z.string(),
  name: z.string(),
  version: z.string(),
  studio_version: z.string(),
  outdated: z.boolean(),
  limits_supported: z.boolean().nullable(),
  reinstall: z.array(ReinstallReasonSchema),
  origin: z.enum(["chart", "ui", "other"]).nullable(),
  report: z
    .strictObject({
      reported_at: iso.nullable(),
      executor: z.enum(["docker", "kubernetes"]),
      platform: z.enum(["kubernetes", "container", "host"]),
      namespace: z.string().nullable(),
      pod_name: z.string().nullable(),
      service_account: z.string().nullable(),
      resources: ResourcesViewSchema.nullable(),
      security: SecurityViewSchema.nullable(),
      build: BuildIsolationViewSchema.nullable(),
    })
    .nullable(),
  live: z
    .strictObject({
      name: z.string(),
      namespace: z.string(),
      image: z.string().nullable(),
      service_account: z.string().nullable(),
      ready: z.boolean(),
      resources: ResourcesViewSchema.nullable(),
      build_resources: ResourcesViewSchema.nullable(),
      security: SecurityViewSchema.nullable(),
    })
    .nullable(),
  live_status: z.enum([
    "ok",
    "not_found",
    "forbidden",
    "unavailable",
    "not_applicable",
  ]),
});
const PolicyCheckSchema = z.strictObject({
  declared: z.boolean().nullable(),
  live: z.boolean().nullable(),
});
const LimitValuesSchema = z.strictObject({
  default: z.record(z.string(), z.string()),
  default_request: z.record(z.string(), z.string()),
  max: z.record(z.string(), z.string()),
});
const QuotaViewSchema = z.strictObject({
  namespace: z.string().nullable(),
  declared: z.record(z.string(), z.string()).nullable(),
  live_found: z.boolean().nullable(),
  live_hard: z.record(z.string(), z.string()).nullable(),
  live_used: z.record(z.string(), z.string()).nullable(),
});
const LimitRangeViewSchema = z.strictObject({
  namespace: z.string().nullable(),
  declared: LimitValuesSchema.nullable(),
  live_found: z.boolean().nullable(),
  live: LimitValuesSchema.nullable(),
});
export const AdminRunnerIsolationSchema = z.strictObject({
  config: z.enum(["helm", "none"]),
  live_read: z.enum(["off", "ok", "partial", "forbidden", "unavailable"]),
  checked_at: iso.nullable(),
  release_namespace: z.string().nullable(),
  chart_runner: z
    .strictObject({
      enabled: z.boolean(),
      executor: z.enum(["docker", "kubernetes"]),
      replicas: z.number().int(),
      namespace: z.string().nullable(),
      service_account: z.string().nullable(),
      resources: ResourcesViewSchema,
      tmp_size_limit: z.string().nullable(),
      storage: z.strictObject({
        kind: z.enum(["pvc", "host_path", "empty_dir"]).nullable(),
        storage_class: z.string().nullable(),
        size: z.string().nullable(),
      }),
      security: SecurityViewSchema,
      docker_socket: z.boolean(),
      // Адрес Gotenberg раннера чарта (офисные задачи); null — без office.
      office_url: z.string().nullable(),
    })
    .nullable(),
  build: z
    .strictObject({
      namespace: z.string().nullable(),
      resources: ResourcesViewSchema,
      work_size_limit: z.string().nullable(),
      tmp_size_limit: z.string().nullable(),
      active_deadline_s: z.number().int().nullable(),
      runtime_class: z.string().nullable(),
      security: SecurityViewSchema,
    })
    .nullable(),
  install_from_ui: z.strictObject({
    enabled: z.boolean(),
    namespace: z.string().nullable(),
    build_namespace: z.string().nullable(),
    service_account: z.string().nullable(),
    storage_class: z.string().nullable(),
    storage_size: z.string(),
    runner: ResourcesViewSchema,
    build: ResourcesViewSchema,
    bounds: z.strictObject({
      max_cpu: z.string(),
      max_memory: z.string(),
      min_runner_cpu: z.string(),
      min_runner_memory: z.string(),
      min_build_cpu: z.string(),
      min_build_memory: z.string(),
    }),
    office_url: z.string().nullable(),
  }),
  network: z
    .strictObject({
      build_deny_all: PolicyCheckSchema,
      ui_build_deny_all: PolicyCheckSchema,
      runner_egress: z.strictObject({
        declared: z.boolean().nullable(),
        live: z.boolean().nullable(),
        dns: z.boolean(),
        studio_port: z.number().int().nullable(),
        api_server_cidrs: z.array(z.string()),
        api_server_ports: z.array(z.number().int()),
        extra_rules: z.number().int(),
        office_port: z.number().int().nullable(),
      }),
    })
    .nullable(),
  quota: QuotaViewSchema.nullable(),
  limit_range: LimitRangeViewSchema.nullable(),
  // Свой namespace подов сборки раннеров из админки (не тот, что у quota и limit_range).
  ui_quota: QuotaViewSchema.nullable(),
  ui_limit_range: LimitRangeViewSchema.nullable(),
  pod_security: z
    .array(
      z.strictObject({
        namespace: z.string(),
        enforce: z.string().nullable(),
        enforce_version: z.string().nullable(),
        warn: z.string().nullable(),
        audit: z.string().nullable(),
      }),
    )
    .nullable(),
  // Встроенный Gotenberg чарта (services.officeConvert); null — выключен или не Helm.
  office_convert: z
    .strictObject({
      url: z.string(),
      image: z.string().nullable(),
      replicas: z.number().int(),
      resources: ResourcesViewSchema,
      network_policy: z.boolean(),
    })
    .nullable(),
});
export const AdminRunnerTokenSchema = z.strictObject({
  id: z.string(),
  label: z.string(),
  created_at: iso,
  expires_at: iso.nullable(),
  max_uses: z.number().int(),
  uses: z.number().int(),
  revoked: z.boolean(),
});
export const CreateAdminRunnerTokenRequestSchema = z.strictObject({
  label: z.string().max(128),
  ttl_hours: z
    .number()
    .int()
    .min(1)
    .max(24 * 30),
  max_uses: z.number().int().min(1).max(100),
});
export const AdminRunnerTokenCreatedSchema = z.strictObject({
  token: AdminRunnerTokenSchema,
  secret: z.string(),
  command: z.string(),
  docker_command: z.string(),
  script_command: z.string(),
  script_command_macos: z.string(),
});
export const AdminRunnerRotatedSchema = z.strictObject({
  runner: AdminRunnerSchema,
  runner_token: z.string(),
  command: z.string(),
  docker_command: z.string(),
  script_command: z.string(),
  script_command_macos: z.string(),
});
export const InstallCapabilitySchema = z.strictObject({
  available: z.boolean(),
  reason: z
    .enum([
      "disabled",
      "no_socket",
      "docker_unreachable",
      "not_in_cluster",
      "no_permission",
    ])
    .nullable(),
});
export const LocalInstallCapabilitiesSchema = z.strictObject({
  docker: InstallCapabilitySchema,
  kubernetes: InstallCapabilitySchema,
});
export const InstallJobSchema = z.strictObject({
  id: z.string(),
  target: z.enum(["docker", "kubernetes", "ssh"]),
  name: z.string(),
  state: z.enum(["running", "succeeded", "failed"]),
  steps: z.array(
    z.strictObject({
      key: z.string(),
      state: z.enum(["pending", "running", "done", "failed", "skipped"]),
      detail: z.string(),
    }),
  ),
  error_code: z.string().nullable(),
  error_detail: z.string(),
  created_at: iso,
  // Откат неудачного обновления: null, если откатывать было нечего; версия,
  // на которую раннер вернули; код причины, если откат тоже не удался.
  rolled_back: z.boolean().nullable().optional(),
  rollback_version: z.string().optional(),
  rollback_error: z.string().nullable().optional(),
  // После отката раннер вышел на связь с прежней версией; null, если не ждали.
  rollback_reconnected: z.boolean().nullable().optional(),
});
/**
 * Установка из админки. `runner_id` пуст, если раннера с ней в Студии нет
 * (отозван или ещё не подключился); `outdated` значит, что он старше Студии.
 */
export const LocalInstanceSchema = z.strictObject({
  target: z.enum(["docker", "kubernetes"]),
  name: z.string(),
  image: z.string(),
  state: z.string(),
  created_at: iso.nullable(),
  runner_id: z.string().nullable(),
  runner_version: z.string().nullable(),
  studio_version: z.string(),
  outdated: z.boolean(),
});
const QUANTITY = /^[0-9]+(\.[0-9]+)?(m|Ki|Mi|Gi|Ti|k|K|M|G|T)?$/;
const quantity = z.string().max(12).regex(QUANTITY);
/** Лимиты раннера в кластере: пустое поле опускается и значит умолчание Helm; границы проверяет бэкенд. */
export const ResourceLimitsRequestSchema = z.strictObject({
  runner_cpu: quantity.optional(),
  runner_memory: quantity.optional(),
  build_cpu: quantity.optional(),
  build_memory: quantity.optional(),
});
export const StartLocalInstallRequestSchema = z.strictObject({
  name: z.string().max(40),
  concurrency: z.number().int().min(1).max(8),
  resources: ResourceLimitsRequestSchema.optional(),
});
export const SshCapabilitySchema = z.strictObject({
  enabled: z.boolean(),
  can_save_credentials: z.boolean(),
});
export const SshHostKeySchema = z.strictObject({
  key_type: z.string(),
  fingerprint: z.string(),
});
export const SshProbeResponseSchema = z.strictObject({
  session_id: z.string(),
  host_key: SshHostKeySchema,
  expires_in_s: z.number().int(),
});
export const SshPlanSchema = z.strictObject({
  session_id: z.string(),
  system: z.strictObject({
    os: z.string(),
    arch: z.string(),
    distro: z.string(),
    has_docker: z.boolean(),
    docker_usable: z.boolean(),
    has_systemd: z.boolean(),
    is_root: z.boolean(),
  }),
  plan: z.array(
    z.strictObject({
      key: z.string(),
      action: z.enum(["run", "skip", "install_docker", "blocked"]),
    }),
  ),
});
export const SavedSshCredentialSchema = z.strictObject({
  id: z.string(),
  label: z.string(),
  host: z.string(),
  port: z.number().int(),
  username: z.string(),
  sudo: z.boolean(),
  auth_kind: z.enum(["password", "key"]),
  key_type: z.string(),
  fingerprint: z.string(),
  created_at: iso,
  last_used_at: iso.nullable(),
  runner_name: z.string().nullable(),
});
export const SshProbeRequestSchema = z.strictObject({
  host: z.string().min(1).max(255),
  port: z.number().int().min(1).max(65535),
  username: z.string().min(1).max(64),
  auth_kind: z.enum(["password", "key"]),
  password: z.string().max(1024).nullable(),
  private_key: z.string().max(16384).nullable(),
  passphrase: z.string().max(1024).nullable(),
  sudo: z.boolean(),
  save_credentials: z.boolean(),
  label: z.string().max(80),
});
export const UpdateAdminRunnerRequestSchema = z.strictObject({
  paused: z.boolean(),
});
export const AdminRunnerPageSchema = pageOf(AdminRunnerSchema);
export const AdminRunnerTokenPageSchema = pageOf(AdminRunnerTokenSchema);
/** Счётчики раннеров для KPI; outdated и newest_version только среди неотозванных. */
export const AdminRunnerSummarySchema = z.strictObject({
  online: z.number().int(),
  paused: z.number().int(),
  stale: z.number().int(),
  offline: z.number().int(),
  revoked: z.number().int(),
  outdated: z.number().int(),
  newest_version: z.string().nullable(),
});

export type JobState =
  "queued" | "running" | "succeeded" | "failed" | "cancelled" | "timed_out";
export type AdminJob = {
  id: string;
  kind: string;
  status: JobState;
  priority: string;
  project_id: string | null;
  project_name: string | null;
  user_id: string;
  user_name: string;
  /** Почта того, кто запустил; null, если человека уже нет. */
  user_email?: string | null;
  org_id?: string | null;
  org_name?: string | null;
  tags: string[];
  runner_id: string | null;
  runner_name: string | null;
  attempt: number;
  max_attempts: number;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  wait_s: number;
  error: string | null;
  /** Маршрут задачи: shared, personal_first, pinned (ИИ через раннер). */
  route?: string | null;
  /** Кто взял попытку: общий раннер или личный. */
  runner_scope?: "shared" | "personal" | null;
  route_reason?: string | null;
  /** Пакет «Собрать все»: задачи одной команды; у одиночной задачи null. */
  batch_id?: string | null;
  batch?: AdminJobBatch | null;
};
/** Пакет «Собрать все» целиком (по всем страницам очереди). */
export type AdminJobBatch = {
  id: string;
  total: number;
  /** Сколько задач пакета в каждом состоянии. */
  by_state: Partial<Record<JobState, number>>;
  /** Когда команда поставила первую задачу. */
  created_at: string;
};
/** Страница очереди: курсор непрозрачный, null на последней; оценка числа только без фильтров. */
export type AdminJobPage = {
  items: AdminJob[];
  next_cursor: string | null;
  total_estimate: number | null;
};
export type AdminQueueSummary = {
  queued: number;
  running: number;
  /** Число задач в каждом состоянии: для счётчиков фильтров. */
  by_state: Record<JobState, number>;
  oldest_queued_age_s: number | null;
  wait_p50_s: number | null;
  wait_p95_s: number | null;
  /** Ожидающие задачи по классам приоритета. */
  classes: { name: string; queued: number }[];
};
export type AdminQuotas = {
  user_concurrent: number | null;
  org_concurrent: number | null;
  max_duration_s: number | null;
};
export type UpdateAdminQuotasRequest = AdminQuotas;
export type ServiceStatus = "ok" | "degraded" | "down" | "unconfigured";
export type AdminService = {
  id: string;
  kind:
    "database" | "storage" | "languagetool" | "onlyoffice" | "runners" | "smtp";
  status: ServiceStatus;
  /** Короткая причина сбоя от сервера. */
  detail: string | null;
  /** Для раннеров: сколько в сети из скольких. */
  online: number | null;
  total: number | null;
};
export type AdminStorage = {
  blob_count: number;
  blob_bytes: number;
  projects: number;
  deleted_projects: number;
  free_bytes: number | null;
  volume_total_bytes: number | null;
  computed_at: string | null;
  owners: { id: string; name: string; projects: number }[];
};

export type AdminRunner = z.infer<typeof AdminRunnerSchema>;
export type AdminRunnerToken = z.infer<typeof AdminRunnerTokenSchema>;
export type CreateAdminRunnerTokenRequest = z.infer<
  typeof CreateAdminRunnerTokenRequestSchema
>;
export type AdminRunnerTokenCreated = z.infer<
  typeof AdminRunnerTokenCreatedSchema
>;
export type InstallCapability = z.infer<typeof InstallCapabilitySchema>;
export type LocalInstallCapabilities = z.infer<
  typeof LocalInstallCapabilitiesSchema
>;
export type InstallJob = z.infer<typeof InstallJobSchema>;
export type LocalInstance = z.infer<typeof LocalInstanceSchema>;
export type StartLocalInstallRequest = z.infer<
  typeof StartLocalInstallRequestSchema
>;
export type SshCapability = z.infer<typeof SshCapabilitySchema>;
export type SshProbeResponse = z.infer<typeof SshProbeResponseSchema>;
export type SshPlan = z.infer<typeof SshPlanSchema>;
export type SavedSshCredential = z.infer<typeof SavedSshCredentialSchema>;
export type SshProbeRequest = z.infer<typeof SshProbeRequestSchema>;
export type AdminRunnerRotated = z.infer<typeof AdminRunnerRotatedSchema>;
export type AdminRunnerPage = z.infer<typeof AdminRunnerPageSchema>;
export type AdminRunnerTokenPage = z.infer<typeof AdminRunnerTokenPageSchema>;
export type AdminRunnerSummary = z.infer<typeof AdminRunnerSummarySchema>;
export type AdminRunnerDeployment = z.infer<typeof AdminRunnerDeploymentSchema>;
export type AdminRunnerIsolation = z.infer<typeof AdminRunnerIsolationSchema>;
export type ReinstallReason = z.infer<typeof ReinstallReasonSchema>;
export type RunnerResourcesView = z.infer<typeof ResourcesViewSchema>;
export type RunnerSecurityView = z.infer<typeof SecurityViewSchema>;
export type RunnerBuildIsolationView = z.infer<typeof BuildIsolationViewSchema>;

// Хранение данных (api/schemas/lifecycle.py): источники роста, сроки хранения, тома и пороги места.
export const LifecycleLevelSchema = z.enum(["ok", "warning", "critical"]);
export const LifecycleLastRunSchema = z.strictObject({
  at: iso.nullable(),
  duration_ms: z.number().int().nullable(),
  removed: z.number().int().nullable(),
  error: z.string().nullable(),
  runs: z.number().int(),
  total_removed: z.number().int().nullable(),
});
export const LifecycleSourceSchema = z.strictObject({
  key: z.string(),
  group: z.enum(["database", "objects", "disk", "logs"]),
  strategy: z.enum([
    "partition_drop",
    "delete_batches",
    "file_sweep",
    "own_task",
    "on_write",
    "infra",
  ]),
  growth: z.enum(["low", "medium", "high"]),
  days: z.number().int().nullable(),
  days_source: z.enum(["admin", "env", "default", "fixed"]),
  min_days: z.number().int().nullable(),
  max_days: z.number().int().nullable(),
  default_days: z.number().int().nullable(),
  editable: z.boolean(),
  run_now: z.boolean(),
  protected: z.boolean(),
  env: z.string().nullable(),
  bytes: z.number().int().nullable(),
  rows: z.number().int().nullable(),
  partitions: z.number().int().nullable(),
  last_run: LifecycleLastRunSchema.nullable(),
});
export const LifecycleVolumeSchema = z.strictObject({
  name: z.string(),
  used_bytes: z.number().int(),
  total_bytes: z.number().int().nullable(),
  free_bytes: z.number().int().nullable(),
  used_ratio: z.number().nullable(),
  level: LifecycleLevelSchema,
});
export const StorageThresholdsSchema = z.strictObject({
  warn_percent: z.number().int(),
  critical_percent: z.number().int(),
});
export const AdminDataLifecycleSchema = z.strictObject({
  sources: z.array(LifecycleSourceSchema),
  volumes: z.array(LifecycleVolumeSchema),
  thresholds: StorageThresholdsSchema,
  level: LifecycleLevelSchema,
  safe_mode: z.boolean(),
});
export const UpdateLifecycleRetentionRequestSchema = z.strictObject({
  days: z.number().int().nullable(),
});
export const LifecycleRunSchema = z.strictObject({
  key: z.string(),
  removed: z.number().int(),
  partitions_dropped: z.number().int(),
  more: z.boolean(),
  error: z.string().nullable(),
});
export type LifecycleLevel = z.infer<typeof LifecycleLevelSchema>;
export type LifecycleSource = z.infer<typeof LifecycleSourceSchema>;
export type LifecycleVolume = z.infer<typeof LifecycleVolumeSchema>;
export type StorageThresholds = z.infer<typeof StorageThresholdsSchema>;
export type AdminDataLifecycle = z.infer<typeof AdminDataLifecycleSchema>;
export type LifecycleRun = z.infer<typeof LifecycleRunSchema>;

// «Освободить место» (storage-cleanup.md, 5.4 и 9.2): все ручные очистки движка одним прогоном на
// сервере. Бэкенда ещё нет (срез B7): эталоны в features/admin-ops/testing/sweepFixtures.ts.
export const LIFECYCLE_SWEEP_STATUSES = [
  "running",
  "cancelling",
  "done",
  "cancelled",
  "error",
  "interrupted",
] as const;
export const LifecycleSweepStatusSchema = z.enum(LIFECYCLE_SWEEP_STATUSES);
export const LifecycleSweepStepSchema = z.strictObject({
  key: z.string(),
  status: z.enum(["pending", "running", "done", "error", "skipped"]),
  removed: z.number().int().nonnegative(),
  partitions_dropped: z.number().int().nonnegative(),
  /** Бюджет кончился раньше: остальное уйдёт на плановом тике. */
  more: z.boolean(),
  /** Замер источника до и после шага; null, пока шаг не дошёл или замер не удался. Шаг, прерванный
   * остановкой api или прогоном `interrupted`, приходит `error` с `error: "interrupted"`, не начатые `skipped`. */
  bytes_before: z.number().int().nonnegative().nullable(),
  bytes_after: z.number().int().nonnegative().nullable(),
  error: z.string().nullable(),
});
export const LifecycleSweepSchema = z.strictObject({
  id: z.string(),
  status: LifecycleSweepStatusSchema,
  /** Id того, кто запустил (без имени); null, если человека уже нет в установке. */
  started_by: z.string().nullable(),
  started_at: iso,
  updated_at: iso,
  finished_at: iso.nullable(),
  steps: z.array(LifecycleSweepStepSchema),
  removed_total: z.number().int().nonnegative(),
  /** Сумма положительных разностей bytes_before и bytes_after (S11). */
  freed_bytes: z.number().int().nonnegative(),
});
/** `GET /data-lifecycle/sweep`: идущий или последний прогон. */
export const LifecycleSweepStateSchema = z.strictObject({
  sweep: LifecycleSweepSchema.nullable(),
});
export const LifecycleSweepPreviewSchema = z.strictObject({
  sources: z.array(
    z.strictObject({
      key: z.string(),
      /** null: срок фиксирован в коде (гостевые сессии), граница всё равно в `cutoff`. */
      days: z.number().int().nullable(),
      /** Граница, по которой источник считал: удаляется всё старше неё; null, если границы нет. */
      cutoff: iso.nullable(),
      /** null: не удалось посчитать за 3 с. */
      count: z.number().int().nonnegative().nullable(),
      /** Счёт упёрся в потолок 100 000: «больше 100 000 записей». */
      capped: z.boolean(),
      bytes: z.number().int().nonnegative().nullable(),
    }),
  ),
  excluded: z.array(
    z.strictObject({
      key: z.string(),
      reason: z.enum(["protected", "own_task", "on_write", "infra"]),
    }),
  ),
  /** У всех источников count = 0: кнопка подтверждения выключена. */
  nothing: z.boolean(),
});
export type LifecycleSweepStatus = z.infer<typeof LifecycleSweepStatusSchema>;
export type LifecycleSweepStep = z.infer<typeof LifecycleSweepStepSchema>;
export type LifecycleSweep = z.infer<typeof LifecycleSweepSchema>;
export type LifecycleSweepState = z.infer<typeof LifecycleSweepStateSchema>;
export type LifecycleSweepPreview = z.infer<typeof LifecycleSweepPreviewSchema>;

/**
 * Схемы раздела 9.2 по именам будущих каталогов contracts/server/fixtures. Срез B7 перенесёт
 * эталоны в contracts/server/fixtures и эту карту в CONTRACT_SCHEMAS (contractSchemas.ts).
 */
export const LIFECYCLE_SWEEP_CONTRACT_SCHEMAS: Record<string, z.ZodType> = {
  LifecycleSweep: LifecycleSweepSchema,
  LifecycleSweepState: LifecycleSweepStateSchema,
  LifecycleSweepPreview: LifecycleSweepPreviewSchema,
};

// Самодиагностика (api/schemas/diagnostics.py): проверки со статусом, причиной и подсказкой, итог, пороги.
export const DiagStatusSchema = z.enum(["ok", "warn", "fail"]);
// Запись о принятии предупреждения: кто, когда, зачем и до какого срока (null: бессрочно).
export const DiagAcceptanceSchema = z.strictObject({
  reason: z.string(),
  by_name: z.string(),
  at: iso,
  until: iso.nullable(),
});
export const DiagCheckSchema = z.strictObject({
  id: z.string(),
  group: z.enum(["data", "compute", "security", "operations"]),
  // null: проверка ещё не выполнялась (свежая установка до первого прохода).
  status: DiagStatusSchema.nullable(),
  reason: z.string().nullable(),
  hint: z.string().nullable(),
  values: z.record(z.string(), z.union([z.string(), z.number()])),
  applicable: z.boolean(),
  // Предупреждение можно принять осознанно (кнопка «Принимаю»).
  acceptable: z.boolean(),
  // Принято и действует: статус остаётся warn, но в итог, меню и уведомления не входит.
  accepted: DiagAcceptanceSchema.nullable(),
  checked_at: iso.nullable(),
  status_since: iso.nullable(),
  duration_ms: z.number().int().nullable(),
});
export const DiagThresholdSchema = z.strictObject({
  name: z.string(),
  value: z.number().int(),
  default: z.number().int(),
  min: z.number().int(),
  max: z.number().int(),
});
export const DiagAcceptedSchema = z.strictObject({
  check: z.string(),
  acceptance: DiagAcceptanceSchema,
  // true: предупреждение сейчас есть и погашено принятием; false: причину уже исправили, запись молчит.
  active: z.boolean(),
});
export const AdminDiagnosticsSchema = z.strictObject({
  overall: DiagStatusSchema,
  enabled: z.boolean(),
  interval_s: z.number(),
  last_tick_at: iso.nullable(),
  checks: z.array(DiagCheckSchema),
  accepted: z.array(DiagAcceptedSchema),
  thresholds: z.array(DiagThresholdSchema),
  notify: z.boolean(),
});
export const UpdateDiagnosticsThresholdsRequestSchema = z.strictObject({
  values: z.record(z.string(), z.number().int()),
  notify: z.boolean(),
});
export const AcceptDiagnosticsRequestSchema = z.strictObject({
  reason: z.string().min(1).max(200),
  until: iso.nullable(),
});
export const RunDiagnosticsRequestSchema = z.strictObject({
  check: z.string().nullable(),
});
export type DiagStatus = z.infer<typeof DiagStatusSchema>;
export type DiagAcceptance = z.infer<typeof DiagAcceptanceSchema>;
export type DiagAccepted = z.infer<typeof DiagAcceptedSchema>;
export type AcceptDiagnosticsRequest = z.infer<
  typeof AcceptDiagnosticsRequestSchema
>;
export type DiagCheck = z.infer<typeof DiagCheckSchema>;
export type DiagThreshold = z.infer<typeof DiagThresholdSchema>;
export type AdminDiagnostics = z.infer<typeof AdminDiagnosticsSchema>;
export type UpdateDiagnosticsThresholdsRequest = z.infer<
  typeof UpdateDiagnosticsThresholdsRequestSchema
>;

/** Вместо раннера поставить сервер ИИ-модели тем же SSH-слоем (docs/design/model-servers.md). */
export type ModelServerInstall = {
  engine: "ollama" | "vllm" | "sglang";
  model: string;
  name?: string;
  exposure: "localhost" | "public";
  acknowledge_public?: boolean;
  force?: boolean;
};
