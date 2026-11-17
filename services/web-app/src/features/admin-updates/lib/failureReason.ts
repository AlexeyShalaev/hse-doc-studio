/**
 * Причина неудачи обновления человеческим языком. Исполнитель отдаёт короткий код (`error_code`) и английский
 * текст; код сводится к одной из групп, у группы в словаре есть заголовок и подсказка «что делать».
 * Сообщения Kubernetes и docker (ErrImagePull, forbidden, manifest unknown) различаются по тексту, потому что
 * исполнитель кладёт их под общим кодом (`precheck_failed`, `patch_failed`).
 */

export type ReasonKey =
  | "image_pull"
  | "image_not_found"
  | "no_permission"
  | "rollout_timeout"
  | "migration_failed"
  | "health_failed"
  | "digest"
  | "signature_invalid"
  | "schema_blocked"
  | "needs_hands"
  | "rollback_failed"
  | "unknown_outcome"
  | "updater_offline"
  | "backup_failed"
  | "disk_space"
  | "cancelled"
  | "cluster_unavailable"
  | "environment"
  | "no_previous"
  | "bad_version"
  | "internal"
  | "unknown";

// Каждый код исполнителя и api. Тест `test_update_error_codes_have_reasons` (api) сверяет этот список с
// кодами в исходниках апдейтера: новый код без строки здесь не пройдёт CI.
export const CODE_REASON: Record<string, ReasonKey> = {
  pull_failed: "image_pull",
  tag_failed: "environment",
  precheck_failed: "image_pull",
  kube_forbidden: "no_permission",
  kube_unavailable: "cluster_unavailable",
  patch_failed: "cluster_unavailable",
  stop_timeout: "rollout_timeout",
  health_timeout: "rollout_timeout",
  health_failed: "health_failed",
  recreate_failed: "health_failed",
  migration_failed: "migration_failed",
  digest_missing: "digest",
  digest_mismatch: "digest",
  digest_unreachable: "digest",
  signature_invalid: "signature_invalid",
  schema_incompatible: "schema_blocked",
  schema_changed: "schema_blocked",
  schema_ahead: "schema_blocked",
  needs_manual_action: "needs_hands",
  rollback_failed: "rollback_failed",
  restore_failed: "rollback_failed",
  updater_lost: "unknown_outcome",
  updater_restarted: "unknown_outcome",
  updater_offline: "updater_offline",
  backup_failed: "backup_failed",
  no_disk_space: "disk_space",
  snapshot_failed: "disk_space",
  cancelled: "cancelled",
  auto_update_disabled: "cancelled",
  no_project: "environment",
  no_api: "environment",
  no_container: "environment",
  api_scaled_down: "environment",
  inspect_failed: "environment",
  no_snapshot_volume: "environment",
  unsupported_container_options: "environment",
  db_unreachable: "environment",
  no_previous_version: "no_previous",
  previous_image_missing: "no_previous",
  snapshot_missing: "no_previous",
  bad_version: "bad_version",
  internal: "internal",
};

// Коды, под которыми исполнитель прячет разные причины: уточняем по тексту сообщения.
const REFINABLE = new Set([
  "precheck_failed",
  "pull_failed",
  "patch_failed",
  "kube_unavailable",
  "health_failed",
  "internal",
]);

const REFINE: [RegExp, ReasonKey][] = [
  [
    /manifest unknown|manifest .*not found|no such image|image .*not found|not found: manifest/i,
    "image_not_found",
  ],
  [
    /ErrImagePull|ImagePullBackOff|failed to pull|pull access denied|toomanyrequests|unauthorized: /i,
    "image_pull",
  ],
  [/forbidden|\bmay not\b|RBAC/i, "no_permission"],
  [
    /did not finish in|did not start in|not healthy after|Unschedulable/i,
    "rollout_timeout",
  ],
];

export const reasonOf = (
  code: string | null,
  message: string | null,
): ReasonKey => {
  const base = code ? CODE_REASON[code] : undefined;
  if (code === null || base === undefined || REFINABLE.has(code)) {
    const text = message ?? "";
    const refined = REFINE.find(([re]) => re.test(text));
    if (refined) return refined[1];
  }
  return base ?? "unknown";
};

/** Причины, при которых итог нельзя читать как «не вышло, но система цела»: нужно проверить версию. */
export const isUnknownOutcome = (reason: ReasonKey): boolean =>
  reason === "unknown_outcome";
