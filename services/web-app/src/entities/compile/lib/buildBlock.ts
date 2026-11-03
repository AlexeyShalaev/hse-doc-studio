import { useCallback } from "react";
import { useDocuments } from "@entities/document";
import { useBuildAvailability, type BuildAvailability } from "@entities/runner";
import { useBootstrap } from "@entities/session";

/**
 * Почему облачная сборка сейчас невозможна: раннеров нет вовсе или нет раннера
 * с нужным тегом. Коды те же, что у отказа сервера при постановке сборки.
 */
export type BuildBlock = {
  reason: "no_runners" | "no_runner_for_tags";
  /** Теги, которые сейчас никто не обслуживает. */
  tags: string[];
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
  return {
    reason: availability.any_runner ? "no_runner_for_tags" : "no_runners",
    tags: missing,
  };
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
