import { useCallback } from "react";
import { useDocuments } from "@entities/document";
import {
  isRunnerGapReason,
  useBuildAvailability,
  type BuildAvailability,
  type RunnerGapReason,
} from "@entities/runner";
import { useBootstrap } from "@entities/session";
import { ApiError } from "@shared/api";

const KNOWN_KINDS = new Set(["tex", "office"]);

/**
 * Теги сборки словами: «офисных документов (Word, PowerPoint)» и т. п. Ключи с
 * пространством имён, поэтому подходит `t` любого пространства.
 */
export const kindsText = (t: (key: string) => string, tags: unknown): string =>
  (Array.isArray(tags) ? tags : [])
    .filter((tag): tag is string => typeof tag === "string")
    .map((tag) =>
      KNOWN_KINDS.has(tag)
        ? t(`documents:compile.unavailable.kind.${tag}`)
        : tag,
    )
    .join(t("documents:compile.unavailable.kindSeparator"));

/** Отказ сервера: для сборки сейчас нет раннера (гонка с опросом доступности). */
export const NO_RUNNER_CODES: ReadonlySet<string> = new Set([
  "no_runners",
  "no_runner_for_tags",
]);

/**
 * Почему облачная сборка сейчас невозможна: раннеров нет вовсе или нет раннера
 * с нужным тегом. Коды те же, что у отказа сервера при постановке сборки.
 */
export type BuildBlock = {
  reason: "no_runners" | "no_runner_for_tags";
  /** Теги, которые сейчас никто не обслуживает. */
  tags: string[];
  /**
   * Почему (по первому такому тегу): личный или облачный раннер на паузе, не в
   * сети, или раннера с тегом нет совсем. Нет поля: сервер причину не прислал.
   */
  cause?: RunnerGapReason;
};

/** null: собрать можно (локальный режим, раннер есть или раннер не нужен). */
export const buildBlockOf = (
  availability: BuildAvailability | undefined,
  buildTags: readonly string[] | undefined,
): BuildBlock | null => {
  if (!availability?.cloud) return null;
  const missing = (buildTags ?? []).filter(
    (tag) => !availability.tags.includes(tag),
  );
  if (missing.length === 0) return null;
  const raw = missing
    .map((tag) => availability.reasons?.[tag])
    .find((value) => value !== undefined);
  const block: BuildBlock = {
    reason: availability.any_runner ? "no_runner_for_tags" : "no_runners",
    tags: missing,
  };
  if (raw !== undefined) {
    block.cause = isRunnerGapReason(raw) ? raw : "no_runner";
  }
  return block;
};

/** Отказ сервера «некому собрать» как блокировка документа: код, теги и причина. */
export const blockOfRefusal = (err: unknown): BuildBlock | null => {
  if (!(err instanceof ApiError) || !NO_RUNNER_CODES.has(err.code)) return null;
  const tags = Array.isArray(err.data?.tags)
    ? err.data.tags.filter((tag): tag is string => typeof tag === "string")
    : [];
  const block: BuildBlock = {
    reason: err.code === "no_runners" ? "no_runners" : "no_runner_for_tags",
    tags,
  };
  const raw = err.data?.reason;
  if (typeof raw === "string") {
    block.cause = isRunnerGapReason(raw) ? raw : "no_runner";
  }
  return block;
};

/**
 * Доступность сборки проекта. Опрашивается только на сервере; пока ответа нет,
 * кнопки не гасим (решать по догадке нельзя, а отказ сервера всё равно придёт).
 */
export const useBuildAvailabilityOf = (projectId: string) => {
  const { data: boot } = useBootstrap();
  const isServer = boot?.mode === "server";
  const { data } = useBuildAvailability(projectId, isServer);
  return isServer ? data : undefined;
};

/** Блокировка сборки для каждого документа проекта по его `build_tags`. */
export const useProjectBuildBlocks = (projectId: string) => {
  const availability = useBuildAvailabilityOf(projectId);
  const { data: documents } = useDocuments(projectId);
  const blockOf = useCallback(
    (docId: string): BuildBlock | null => {
      const doc = documents?.find((d) => d.id === docId);
      return buildBlockOf(availability, doc?.build_tags);
    },
    [availability, documents],
  );
  return { availability, documents, blockOf };
};
