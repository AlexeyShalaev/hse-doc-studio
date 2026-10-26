import type { Probe } from "@entities/git-remote";
import {
  outcomeFromError,
  outcomeFromProbe,
  type CheckIssue,
} from "./probeOutcome";

// Что показать после проверки адреса при клонировании: чистые функции, без
// интерфейса. Проект можно клонировать, если в репозитории есть проект Студии;
// пустой репозиторий и чужие данные останавливают на этом шаге.

export type CloneAccess = "full" | "read_only" | "files_only";

/** Почему проект откроется не полностью. */
export type CloneAccessReason = "schema_newer" | "template_missing";

export type CloneVerdict =
  | {
      kind: "ready";
      access: CloneAccess;
      reasons: CloneAccessReason[];
      requiredStudio: string | null;
    }
  | { kind: "empty" }
  | { kind: "not_studio" }
  | { kind: "error"; issue: CheckIssue };

export const isCloneAccess = (value: unknown): value is CloneAccess =>
  value === "full" || value === "read_only" || value === "files_only";

/** Как проект откроется после клонирования. Без шаблона он открывается на чтение. */
export const accessOf = (
  schemaAccess: string | null | undefined,
  templateAvailable: boolean | null | undefined,
): { access: CloneAccess; reasons: CloneAccessReason[] } => {
  const reasons: CloneAccessReason[] = [];
  let access: CloneAccess = "full";
  if (isCloneAccess(schemaAccess) && schemaAccess !== "full") {
    access = schemaAccess;
    reasons.push("schema_newer");
  }
  if (templateAvailable === false) {
    if (access === "full") access = "read_only";
    reasons.push("template_missing");
  }
  return { access, reasons };
};

export const cloneVerdictFromProbe = (probe: Probe): CloneVerdict => {
  const outcome = outcomeFromProbe(probe);
  if (outcome.kind === "error") return outcome;
  if (probe.relation === "empty" || probe.empty) return { kind: "empty" };
  if (probe.relation === "not_studio_project") return { kind: "not_studio" };
  // Связь с проектом на этом шаге не задана, остальные значения значат «проект Студии».
  if (probe.relation === "unknown" || !probe.project) {
    return {
      kind: "error",
      issue: {
        code: "git_error",
        detail: "",
        hostKeys: [],
        requiredStudio: null,
        canAdopt: null,
      },
    };
  }
  const { access, reasons } = accessOf(
    probe.schema_access,
    probe.template_available,
  );
  return {
    kind: "ready",
    access,
    reasons,
    requiredStudio: probe.required_studio ?? null,
  };
};

/** Исход по ошибке запроса проверки: неверный адрес, сеть, отказ сервера. */
export const cloneVerdictFromError = (error: unknown): CloneVerdict => {
  const outcome = outcomeFromError(error);
  if (outcome.kind === "error") return outcome;
  if (outcome.kind === "not_studio") return { kind: "not_studio" };
  return {
    kind: "error",
    issue: {
      code: "git_error",
      detail: "",
      hostKeys: [],
      requiredStudio: null,
      canAdopt: null,
    },
  };
};
