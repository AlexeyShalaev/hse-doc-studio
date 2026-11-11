import { Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@shared/ui";
import type { RunnerDiskReport } from "../model/runnerDisk.schema";
import {
  diskConfirmPlan,
  type DiskPlanGroup,
  type RunnerDiskConfirmKind,
} from "../lib/runnerDiskConfirm";
import { DiskRefRow } from "./RunnerDiskBlocks";
import { diskSize } from "./format";

// Подтверждение очистки на месте блоков (4.1): что удалится и сколько по последнему замеру.
// Окно поверх окна на телефоне неудобно, поэтому подтверждение занимает тело диалога.

const GROUP_LABEL = {
  old_versions: "old.title",
  unused_images: "unused.title",
  build_cache: "cache.title",
  dangling_images: "dangling.title",
  stopped_containers: "stopped.title",
  runner_cache: "runnerCache.title",
} as const;

const Group = ({
  group,
  report,
  showHeader,
}: {
  group: DiskPlanGroup;
  report: RunnerDiskReport;
  showHeader: boolean;
}) => {
  const { t } = useTranslation("runnerDisk");
  const docker = report.docker;
  const lines: { key: string; label: string; bytes: number }[] = [];
  if (group.target === "runner_cache") {
    lines.push(
      {
        key: "blobs",
        label: t("category.runnerBlobs"),
        bytes: report.cache.blobs.bytes,
      },
      {
        key: "workspaces",
        label: t("category.runnerWorkspaces"),
        bytes: report.cache.workspaces.bytes,
      },
    );
  } else if (group.target === "dangling_images" && docker) {
    lines.push({
      key: "dangling",
      label: t("dangling.detail", {
        count: docker.dangling.count,
        size: diskSize(docker.dangling.bytes),
      }),
      bytes: docker.dangling.bytes,
    });
  } else if (group.target === "stopped_containers" && docker) {
    lines.push({
      key: "stopped",
      label: t("stopped.detail", {
        count: docker.stopped_containers.count,
        size: diskSize(docker.stopped_containers.bytes),
      }),
      bytes: docker.stopped_containers.bytes,
    });
  } else if (group.target === "build_cache") {
    lines.push({
      key: "cache",
      label: t("cache.title"),
      bytes: group.bytes,
    });
  }
  return (
    <div
      className="flex flex-col"
      style={{ gap: "0.25rem" }}
      data-testid={`runner-disk-confirm-${group.target}`}
    >
      {showHeader && (
        <div
          className="flex items-baseline justify-between"
          style={{ gap: "0.5rem", fontSize: "0.75rem", fontWeight: 600 }}
        >
          <span>{t(GROUP_LABEL[group.target])}</span>
          <span className="mono">{diskSize(group.bytes)}</span>
        </div>
      )}
      {group.items.map((item) => (
        <DiskRefRow
          key={`${item.kind ?? "image"}-${item.ref}`}
          refName={item.ref}
          bytes={item.bytes}
          note={
            item.kind
              ? item.rollback
                ? `${t(`old.kind.${item.kind}`)}, ${t("confirm.rollbackItem")}`
                : t(`old.kind.${item.kind}`)
              : undefined
          }
        />
      ))}
      {(!showHeader || group.target === "runner_cache") &&
        lines.map((line) => (
          <div
            key={line.key}
            className="flex flex-wrap items-baseline justify-between"
            style={{ gap: "0.125rem 0.5rem", fontSize: "0.71875rem" }}
          >
            <span>{line.label}</span>
            <span className="mono dim">{diskSize(line.bytes)}</span>
          </div>
        ))}
    </div>
  );
};

export const RunnerDiskConfirm = ({
  kind,
  report,
  runnerName,
  canIncludeRollback,
  includeRollback,
  onIncludeRollback,
  personal,
  pending,
  onConfirm,
  onBack,
}: {
  kind: RunnerDiskConfirmKind;
  report: RunnerDiskReport;
  runnerName: string;
  /** Флажок отката: владелец личного раннера и админ общего (S8). */
  canIncludeRollback: boolean;
  includeRollback: boolean;
  onIncludeRollback: (value: boolean) => void;
  /** Личный раннер в админке: владелец получит уведомление. */
  personal: boolean;
  pending: boolean;
  onConfirm: () => void;
  onBack: () => void;
}) => {
  const { t } = useTranslation("runnerDisk");
  const plan = diskConfirmPlan(report, kind, includeRollback);
  const rollback = report.docker?.available
    ? report.docker.old_versions.rollback
    : null;
  const showRollback =
    kind === "old_versions" && canIncludeRollback && rollback !== null;
  const all = kind === "all";
  return (
    <div
      className="flex flex-col"
      style={{ gap: "0.75rem" }}
      data-testid="runner-disk-confirm"
      role="group"
      aria-labelledby="runner-disk-confirm-title"
    >
      <div className="flex flex-col" style={{ gap: "0.375rem" }}>
        <h3
          id="runner-disk-confirm-title"
          style={{ margin: 0, fontSize: "0.875rem", fontWeight: 600 }}
        >
          {all
            ? t("confirm.title", { name: runnerName })
            : t(`confirm.titles.${kind}`)}
        </h3>
        <p
          className="dim"
          style={{ margin: 0, fontSize: "0.75rem", lineHeight: 1.5 }}
        >
          {all ? t("confirm.body") : t("confirm.targetBody")}
        </p>
      </div>

      <div
        className="flex flex-col"
        style={{
          gap: "0.625rem",
          padding: "0.625rem 0.75rem",
          borderRadius: "var(--r-3)",
          border: "1px solid var(--border)",
          background: "var(--bg-1)",
          maxHeight: "18rem",
          overflow: "auto",
        }}
      >
        {plan.groups.map((group) => (
          <Group
            key={group.target}
            group={group}
            report={report}
            showHeader={all}
          />
        ))}
      </div>

      {plan.targets.includes("runner_cache") && (
        <p className="dim" style={{ margin: 0, fontSize: "0.71875rem" }}>
          {t("confirm.runnerCacheNote")}
        </p>
      )}

      {showRollback && (
        <label
          className="flex items-start"
          style={{ gap: "0.5rem", fontSize: "0.75rem" }}
        >
          <input
            type="checkbox"
            checked={includeRollback}
            style={{ marginTop: "0.1875rem" }}
            data-testid="runner-disk-rollback"
            onChange={(e) => {
              onIncludeRollback(e.target.checked);
            }}
          />
          <span style={{ minWidth: 0, overflowWrap: "anywhere" }}>
            {t("confirm.rollback", {
              ref: rollback.ref,
              size: diskSize(rollback.size_bytes),
            })}
            <span
              style={{
                display: "block",
                fontSize: "0.6875rem",
                color: "var(--c-warn)",
              }}
            >
              {t("confirm.rollbackHint")}
            </span>
          </span>
        </label>
      )}

      {personal && (
        <p className="dim" style={{ margin: 0, fontSize: "0.71875rem" }}>
          {t("confirm.personal")}
        </p>
      )}

      <div
        className="flex flex-wrap items-center justify-between"
        style={{ gap: "0.5rem" }}
      >
        <span style={{ fontSize: "0.75rem", fontWeight: 600 }}>
          {t("confirm.total", { size: diskSize(plan.bytes) })}
        </span>
        <span
          className="flex flex-wrap items-center"
          style={{ gap: "0.5rem", marginLeft: "auto" }}
        >
          <Button type="button" variant="ghost" onClick={onBack}>
            {t("confirm.cancel")}
          </Button>
          <Button
            type="button"
            variant="danger"
            disabled={pending || plan.bytes === 0}
            onClick={onConfirm}
            data-testid="runner-disk-confirm-action"
          >
            <Trash2 size="0.75rem" aria-hidden="true" />
            {kind === "old_versions" ||
            kind === "unused_images" ||
            kind === "dangling_images"
              ? t("confirm.remove")
              : t("confirm.action")}
          </Button>
        </span>
      </div>
    </div>
  );
};
