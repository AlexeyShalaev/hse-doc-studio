import { useState } from "react";
import { ArrowUpCircle, RefreshCw, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Badge, Button, Notice, Spinner } from "@shared/ui";
import { DiskUsageOverview, buildDiskSegments } from "@entities/docker-system";
import type {
  DiskTarget,
  RunnerDiskAutoRequest,
  RunnerDiskCleanupRequest,
  RunnerDiskReport,
  RunnerDiskView,
} from "../model/runnerDisk.schema";
import {
  diskTargetBytes,
  hasDiskTarget,
  isDiskCommandActive,
  runnerDiskMode,
  runnerDiskTotals,
} from "../lib/runnerDiskLib";
import {
  diskCleanupRequest,
  type RunnerDiskConfirmKind,
} from "../lib/runnerDiskConfirm";
import {
  DockerBlocks,
  RunnerCacheBlock,
  VolumesBlock,
  type DiskBlockAction,
} from "./RunnerDiskBlocks";
import { RunnerDiskAutoBlock } from "./RunnerDiskAutoBlock";
import { RunnerDiskConfirm } from "./RunnerDiskConfirm";
import { RunnerDiskJob } from "./RunnerDiskJob";
import { diskSize, diskWhen } from "./format";

// «Диск» раннера без окна (docs/design/storage-cleanup.md, 4.1): замер, полоса по категориям,
// блоки с очисткой, подтверждение, ход и итог. Данные и действия приходят снаружи, поэтому
// панель рисуют и диалог (RunnerDiskDialog), и галереи, и тесты.

/** Кэш раннера на полосе: свой тон (--chart-6), рабочие копии светлее (--chart-7). */
const RUNNER_BLOBS_COLOR = "var(--chart-6)";
const RUNNER_WORKSPACES_COLOR = "var(--chart-7)";

export type RunnerDiskPanelProps = {
  view: RunnerDiskView;
  runnerName: string;
  /** Версия раннера для заглушки «Обновите раннер»; без неё текст без номера. */
  runnerVersion?: string | null | undefined;
  /** Раннер установлен из админки: у заглушки кнопка «Обновить раннер» (как в «Как развёрнут»). */
  onUpgrade?: (() => void) | undefined;
  /** «Обновить»: поставить замер. */
  onRefresh: () => void;
  onClean: (request: RunnerDiskCleanupRequest) => void;
  /** «Остановить после текущего шага» (и отмена до того, как раннер забрал команду). */
  onCancel: (commandId: string) => void;
  /** Сохранить автоочистку (только админка, только общий раннер); без него блок только показывает. */
  onSaveAuto?: ((request: RunnerDiskAutoRequest) => void) | undefined;
  /** Запросы, которые уже ушли: кнопки не нажимаются дважды. */
  pending?:
    | { refresh?: boolean; clean?: boolean; cancel?: boolean; auto?: boolean }
    | undefined;
  /** Текст отказа последнего действия (409 runner_offline и прочие). */
  error?: string | null | undefined;
  /** Галерея и тесты: открыть сразу с подтверждением. */
  initialConfirm?: RunnerDiskConfirmKind | null | undefined;
  initialIncludeRollback?: boolean | undefined;
};

const segmentsOf = (report: RunnerDiskReport, label: (key: string) => string) =>
  buildDiskSegments(
    [
      ...(report.docker?.available ? report.docker.categories : []),
      {
        key: "runnerBlobs",
        bytes: report.cache.blobs.bytes,
        color: RUNNER_BLOBS_COLOR,
      },
      {
        key: "runnerWorkspaces",
        bytes: report.cache.workspaces.bytes,
        color: RUNNER_WORKSPACES_COLOR,
      },
    ],
    label,
  );

export const RunnerDiskPanel = ({
  view,
  runnerName,
  runnerVersion = null,
  onUpgrade,
  onRefresh,
  onClean,
  onCancel,
  onSaveAuto,
  pending = {},
  error = null,
  initialConfirm = null,
  initialIncludeRollback = false,
}: RunnerDiskPanelProps) => {
  const { t } = useTranslation("runnerDisk");
  const [confirm, setConfirm] = useState<RunnerDiskConfirmKind | null>(
    initialConfirm,
  );
  const [includeRollback, setIncludeRollback] = useState(
    initialIncludeRollback,
  );
  const [hidden, setHidden] = useState<string | null>(null);

  const mode = runnerDiskMode(view);
  const report = view.report;
  const command = view.command?.kind === "disk.cleanup" ? view.command : null;
  const active = isDiskCommandActive(command);
  const showJob = command !== null && (active || hidden !== command.id);
  const personal = view.personal_owner !== null;
  const canClean = view.can_clean && !active && !pending.clean;

  if (mode === "outdated") {
    return (
      <div data-testid="runner-disk" data-mode={mode}>
        <div
          className="flex flex-col items-start"
          data-testid="runner-disk-outdated"
          style={{
            gap: "0.5rem",
            padding: "1rem",
            borderRadius: "var(--r-3)",
            border: "1px dashed var(--border-strong)",
          }}
        >
          <span style={{ fontSize: "0.875rem", fontWeight: 600 }}>
            {t("outdated.title")}
          </span>
          <span
            className="dim"
            style={{ fontSize: "0.75rem", lineHeight: 1.5 }}
          >
            {runnerVersion
              ? t("outdated.body", { version: runnerVersion })
              : t("outdated.bodyUnknown")}{" "}
            {t("outdated.min", { version: view.min_version })}
          </span>
          {onUpgrade && (
            <Button
              type="button"
              size="sm"
              variant="primary"
              onClick={onUpgrade}
              data-testid="runner-disk-upgrade"
            >
              <ArrowUpCircle size="0.75rem" aria-hidden="true" />
              {t("outdated.upgrade")}
            </Button>
          )}
        </div>
      </div>
    );
  }

  const close = () => {
    setConfirm(null);
    setIncludeRollback(false);
  };

  const ask = (kind: RunnerDiskConfirmKind) => {
    setIncludeRollback(false);
    setConfirm(kind);
  };

  const actionFor = (target: DiskTarget, label: string): DiskBlockAction => {
    const bytes = report ? diskTargetBytes(report, target) : 0;
    const rollbackOnly =
      target === "old_versions" &&
      view.can_include_rollback &&
      report?.docker?.old_versions.rollback != null;
    return {
      label,
      disabled:
        !canClean ||
        !hasDiskTarget(report, target) ||
        (bytes === 0 && !rollbackOnly),
      onClick: () => {
        ask(target);
      },
    };
  };

  const refreshDisabled =
    !view.online || view.measuring || active || Boolean(pending.refresh);

  const header = (
    <div
      className="flex flex-wrap items-center justify-between"
      style={{ gap: "0.375rem 0.75rem" }}
    >
      <span
        className="flex flex-wrap items-center"
        style={{ gap: "0.375rem", fontSize: "0.75rem" }}
      >
        {view.measuring ? (
          <span
            className="flex items-center dim"
            style={{ gap: "0.375rem" }}
            data-testid="runner-disk-measuring"
          >
            <Spinner size="sm" />
            {t("measuring")}
          </span>
        ) : (
          report && (
            <span className="dim" data-testid="runner-disk-measured">
              {t("measuredAt", { when: diskWhen(report.measured_at) })}
            </span>
          )
        )}
        {view.stale && report && (
          <Badge variant="warning" data-testid="runner-disk-stale">
            {t("stale")}
          </Badge>
        )}
      </span>
      <Button
        type="button"
        size="xs"
        variant="secondary"
        disabled={refreshDisabled}
        onClick={onRefresh}
        data-testid="runner-disk-refresh"
      >
        <RefreshCw size="0.6875rem" aria-hidden="true" />
        {t("refresh")}
      </Button>
    </div>
  );

  const notices = (
    <>
      {personal && view.personal_owner && (
        <Notice
          tone="info"
          role="status"
          text={t("personal", { owner: view.personal_owner.name })}
        />
      )}
      {!view.online && (
        <Notice
          tone="warn"
          role="status"
          text={
            view.last_seen_at
              ? t("offline", { when: diskWhen(view.last_seen_at) })
              : t("offlineNever")
          }
        />
      )}
      {mode === "kubernetes" && (
        <Notice
          tone="info"
          text={
            <>
              <strong style={{ display: "block", fontWeight: 600 }}>
                {t("kubernetes.title")}
              </strong>
              {t("kubernetes.body")}
            </>
          }
        />
      )}
      {mode === "desktop" && <Notice tone="info" text={t("desktop.body")} />}
      {mode === "docker_unavailable" && (
        <Notice tone="warn" text={t("dockerUnavailable")} />
      )}
      {error && <Notice tone="err" role="alert" text={error} />}
    </>
  );

  return (
    <div
      className="flex flex-col"
      style={{ gap: "0.75rem", minWidth: 0 }}
      data-testid="runner-disk"
      data-mode={mode}
    >
      <p
        className="dim"
        style={{ margin: 0, fontSize: "0.75rem", lineHeight: 1.5 }}
      >
        {t("lead")}
      </p>
      {header}
      {notices}

      {report === null ? (
        <div
          data-testid="runner-disk-no-report"
          className="flex flex-col"
          style={{
            gap: "0.25rem",
            padding: "1rem",
            borderRadius: "var(--r-3)",
            border: "1px dashed var(--border-strong)",
            fontSize: "0.75rem",
          }}
        >
          <span style={{ fontWeight: 600 }}>{t("noReport")}</span>
          {view.online && <span className="dim">{t("noReportHint")}</span>}
        </div>
      ) : confirm !== null ? (
        <RunnerDiskConfirm
          kind={confirm}
          report={report}
          runnerName={runnerName}
          canIncludeRollback={view.can_include_rollback}
          includeRollback={includeRollback}
          onIncludeRollback={setIncludeRollback}
          personal={personal}
          pending={Boolean(pending.clean)}
          onBack={close}
          onConfirm={() => {
            onClean(diskCleanupRequest(report, confirm, includeRollback));
            close();
          }}
        />
      ) : (
        <ReportBody
          view={view}
          report={report}
          mode={mode}
          personal={personal}
          canClean={canClean}
          actionFor={actionFor}
          job={
            showJob ? (
              <RunnerDiskJob
                command={command}
                cancelling={Boolean(pending.cancel)}
                onCancel={() => {
                  onCancel(command.id);
                }}
                onHide={() => {
                  setHidden(command.id);
                }}
              />
            ) : null
          }
          onCleanAll={() => {
            ask("all");
          }}
        />
      )}
      {view.auto !== null && confirm === null && (
        <RunnerDiskAutoBlock
          // Новая настройка с сервера (сохранили в другой вкладке) сбрасывает правку в поле.
          key={`${String(view.auto.enabled)}:${String(view.auto.min_free_percent)}`}
          auto={view.auto}
          onSave={onSaveAuto}
          pending={Boolean(pending.auto)}
        />
      )}
    </div>
  );
};

const ReportBody = ({
  view,
  report,
  mode,
  personal,
  canClean,
  actionFor,
  job,
  onCleanAll,
}: {
  view: RunnerDiskView;
  report: RunnerDiskReport;
  mode: ReturnType<typeof runnerDiskMode>;
  personal: boolean;
  canClean: boolean;
  actionFor: (target: DiskTarget, label: string) => DiskBlockAction;
  job: React.ReactNode;
  onCleanAll: () => void;
}) => {
  const { t } = useTranslation("runnerDisk");
  const totals = runnerDiskTotals(report);
  const docker =
    mode === "docker" && report.docker?.available ? report.docker : null;
  const active = isDiskCommandActive(view.command);
  return (
    <>
      <DiskUsageOverview
        segments={segmentsOf(report, (key) => t(`category.${key}`))}
        title={
          <span data-testid="runner-disk-total">
            {t("total", {
              used: diskSize(totals.used),
              cleanable: diskSize(totals.cleanable),
            })}
          </span>
        }
      />
      {report.volume && (
        <span
          className="dim"
          style={{ fontSize: "0.71875rem" }}
          data-testid="runner-disk-volume"
        >
          {t("volume", {
            free: diskSize(report.volume.free_bytes),
            total: diskSize(report.volume.total_bytes),
          })}
        </span>
      )}

      {job}

      {docker && (
        <DockerBlocks
          report={report}
          docker={docker}
          personal={personal}
          actionFor={actionFor}
        />
      )}
      <RunnerCacheBlock
        report={report}
        action={actionFor("runner_cache", t("runnerCache.action"))}
      />
      {docker && <VolumesBlock docker={docker} />}

      {!active && (
        <div
          className="flex flex-wrap items-center justify-between"
          style={{
            gap: "0.5rem 0.75rem",
            paddingTop: "0.25rem",
            borderTop: "1px solid var(--border-soft)",
          }}
        >
          <span
            className="dim"
            style={{ fontSize: "0.71875rem", flex: "1 1 14rem" }}
          >
            {totals.cleanable === 0
              ? t("nothingToClean")
              : docker
                ? t("cleanAllHint")
                : t("cleanAllHintCache")}
          </span>
          <Button
            type="button"
            variant="primary"
            disabled={!canClean || totals.cleanable === 0}
            onClick={onCleanAll}
            data-testid="runner-disk-clean-all"
          >
            <Trash2 size="0.75rem" aria-hidden="true" />
            {t("cleanAll")}
          </Button>
        </div>
      )}
    </>
  );
};
