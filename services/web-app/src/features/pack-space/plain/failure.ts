import type { TFunction } from "i18next";
import { ApiError } from "@shared/api";

// Сбой сборки PDF человеческими словами (pack-studio-ux.md, принцип P5): по коду причины выбирается
// заголовок и «Что делать», а сырой текст сервера (Docker, пути, исключения) уходит в «Технические
// подробности». Коды те же, что у записи сборки (`core/compile/failure.py`, `core/pack_studio/preview.py`);
// тест сверяет список с сервером: новый код без слов ломает его.

export const FAILURE_FAMILIES = {
  docker: ["docker_unavailable"],
  image: ["image_missing"],
  environment: [
    "docker_exec_failed",
    "host_path_unmapped",
    "build_dir_failed",
    "unsupported_engine",
    "compile_setup_error",
  ],
  nobuilder: [
    "no_runners",
    "no_runner_for_tags",
    "runner_paused",
    "runner_offline",
    "build_backend_unavailable",
  ],
  lost: [
    "runner_lost",
    "lease_lost",
    "runner_shutdown",
    "job_lost",
    "idle_timeout",
    "staging_failed",
    "executor_crashed",
    "compile_crashed",
    "handler_crashed",
    "blob_unavailable",
    "storage_unreachable",
    "artifact_upload_failed",
    "artifact_invalid",
  ],
  memory: ["build_out_of_memory"],
  space: ["build_storage_exceeded", "disk_full"],
  slow: ["timed_out", "job_timeout"],
  quota: ["quota_exceeded", "preview_quota"],
  text: ["build_failed"],
  render: ["render_failed"],
  nopdf: ["pdf_missing"],
  font: ["font_missing"],
  stopped: ["cancelled", "superseded", "restarted", "interrupted"],
  result: [
    "output_not_allowed",
    "output_unsafe_path",
    "output_missing",
    "output_mismatch",
    "output_changed",
    "apply_failed",
    "manifest_error",
    "manifest_file_too_large",
    "manifest_too_large",
    "manifest_file_missing",
    "manifest_file_changed",
    "manifest_unsafe_path",
  ],
} as const;
export type FailureFamily =
  keyof typeof FAILURE_FAMILIES | "network" | "unknown";

/** Все коды, которым слои слов дали отдельное объяснение. */
export const KNOWN_FAILURE_CODES: readonly string[] =
  Object.values(FAILURE_FAMILIES).flat();

export const familyOf = (
  code: string | null,
  offline = false,
): FailureFamily => {
  if (offline) return "network";
  if (code === null) return "unknown";
  for (const [family, codes] of Object.entries(FAILURE_FAMILIES)) {
    if ((codes as readonly string[]).includes(code)) {
      return family as FailureFamily;
    }
  }
  return "unknown";
};

/** Причина сбоя в том виде, как её отдают запись сборки или ответ с ошибкой. */
export type FailureInput = {
  code: string | null;
  detail: string | null;
  /** Связи с сервером нет (запрос не дошёл). */
  offline?: boolean;
};

export type PlainFailure = {
  family: FailureFamily;
  title: string;
  /** «Что делать». */
  how: string;
  tech: { label: string; value: string }[];
};

/** Причина из записи сборки и из ошибки запроса: что есть, то и берётся. */
export const failureInput = (
  error: unknown,
  buildError: { code: string; detail?: string | null } | null | undefined,
): FailureInput => {
  if (buildError) {
    return { code: buildError.code, detail: buildError.detail ?? null };
  }
  if (error instanceof ApiError) {
    return {
      code: error.code,
      detail: error.detail,
      offline: error.status === 0,
    };
  }
  return { code: null, detail: null };
};

export const plainFailure = (
  input: FailureInput,
  t: TFunction,
): PlainFailure => {
  const family = familyOf(input.code, input.offline === true);
  const tech: PlainFailure["tech"] = [];
  if (input.code !== null && input.code !== "") {
    tech.push({ label: t("plain.tech.code"), value: input.code });
  }
  if (input.detail !== null && input.detail !== "") {
    tech.push({ label: t("plain.tech.message"), value: input.detail });
  }
  return {
    family,
    title: t(`plain.failure.${family}.title`),
    how: t(`plain.failure.${family}.how`),
    tech,
  };
};
