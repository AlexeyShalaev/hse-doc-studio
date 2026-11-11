import type {
  DiskOldItem,
  DiskTarget,
  RunnerDiskCleanupRequest,
  RunnerDiskReport,
} from "../model/runnerDisk.schema";
import {
  cleanAllTargets,
  diskTargetBytes,
  runnerDiskTotals,
} from "./runnerDiskLib";

// Что перечисляет подтверждение очистки (docs/design/storage-cleanup.md, 4.1): цели, поимённо
// образы и контейнеры, размеры из последнего замера. Раннер всё равно строит план по свежему
// замеру (S1), поэтому список это обещание «не больше этого», а не точный план.

/** Что подтверждают: одна цель из блока или «Очистить всё». */
export type RunnerDiskConfirmKind = DiskTarget | "all";

export type DiskPlanItem = {
  ref: string;
  bytes: number;
  /** У старых версий: образ Студии, образ сервиса или контейнер. */
  kind?: DiskOldItem["kind"];
  /** Предыдущая версия, попавшая в план флажком. */
  rollback?: boolean;
};

export type DiskPlanGroup = {
  target: DiskTarget;
  bytes: number;
  /** Образы и контейнеры поимённо; у кэшей пусто. */
  items: DiskPlanItem[];
};

export type DiskConfirmPlan = {
  targets: DiskTarget[];
  groups: DiskPlanGroup[];
  bytes: number;
};

const itemsOf = (
  report: RunnerDiskReport,
  target: DiskTarget,
  includeRollback: boolean,
): DiskPlanItem[] => {
  const docker = report.docker?.available ? report.docker : null;
  if (!docker) return [];
  if (target === "old_versions") {
    const { items, rollback } = docker.old_versions;
    return [
      ...items.map((i) => ({ ref: i.ref, bytes: i.size_bytes, kind: i.kind })),
      ...(includeRollback && rollback
        ? [
            {
              ref: rollback.ref,
              bytes: rollback.size_bytes,
              kind: rollback.kind,
              rollback: true,
            },
          ]
        : []),
    ];
  }
  if (target === "unused_images") {
    return docker.unused_images.map((i) => ({
      ref: i.ref,
      bytes: i.size_bytes,
    }));
  }
  return [];
};

/**
 * План подтверждения. «Очистить всё» шлёт все цели, которые раннер умеет сейчас, а
 * показывает только непустые; откат в него не входит никогда.
 */
export const diskConfirmPlan = (
  report: RunnerDiskReport,
  kind: RunnerDiskConfirmKind,
  includeRollback = false,
): DiskConfirmPlan => {
  if (kind === "all") {
    const targets = cleanAllTargets(report);
    return {
      targets,
      groups: targets
        .map((target) => ({
          target,
          bytes: diskTargetBytes(report, target),
          items: itemsOf(report, target, false),
        }))
        .filter((g) => g.bytes > 0),
      bytes: runnerDiskTotals(report).cleanable,
    };
  }
  const rollback = kind === "old_versions" && includeRollback;
  const bytes = diskTargetBytes(report, kind, rollback);
  return {
    targets: [kind],
    groups: [{ target: kind, bytes, items: itemsOf(report, kind, rollback) }],
    bytes,
  };
};

/** Тело запроса очистки: откат только у старых версий и только там, где он разрешён. */
export const diskCleanupRequest = (
  report: RunnerDiskReport,
  kind: RunnerDiskConfirmKind,
  includeRollback: boolean,
): RunnerDiskCleanupRequest => ({
  targets: diskConfirmPlan(report, kind).targets,
  include_rollback:
    kind === "old_versions" &&
    includeRollback &&
    report.docker?.old_versions.rollback != null,
});
