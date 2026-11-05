import { AlertTriangle, RefreshCw } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  silentMinutes,
  useCompileStreamStore,
  useNowWhile,
  useProjectBuildSummary,
} from "@entities/compile";

/** Тревога о зависании: минуты считаются с последнего вывода запущенной сборки, а не с нажатия «Собрать». */
const StallAlert = ({ projectId }: { projectId: string }) => {
  const { t } = useTranslation("workbench");
  const now = useNowWhile(true);
  const streams = useCompileStreamStore((s) => s.streams);
  const prefix = `${projectId}::`;
  const silentMs = Object.entries(streams)
    .filter(
      ([k, slot]) =>
        k.startsWith(prefix) && slot.status === "running" && slot.isStalled,
    )
    .reduce((max, [, slot]) => Math.max(max, now - slot.lastEventAt), 0);
  return (
    <div
      className="flex items-start gap-2"
      role="alert"
      data-testid="build-stall-banner"
      style={{
        margin: "0 0.125rem 0.5rem",
        padding: "0.375rem 0.5rem",
        fontSize: "0.65625rem",
        lineHeight: 1.4,
        background: "var(--c-err-soft, rgba(239, 68, 68, 0.08))",
        border: "1px solid var(--c-err)",
        color: "var(--c-err)",
        borderRadius: "0.25rem",
      }}
    >
      <AlertTriangle size="0.75rem" style={{ flexShrink: 0, marginTop: 1 }} />
      <span style={{ minWidth: 0, overflowWrap: "anywhere" }}>
        {t("documents.stalledWarning", { count: silentMinutes(silentMs) })}
      </span>
    </div>
  );
};

export type BuildStatusNoticeProps = {
  projectId: string;
  /** Идёт ли в проекте хоть одна сборка (слот, запрос или статус документа). */
  isCompiling: boolean;
};

/**
 * Плашка состояния сборок над списком документов. Красная только для запущенной раннером и замолчавшей сборки;
 * очередь показывается спокойной серой строкой: раннер берёт задачи по `concurrency`, остальные честно ждут.
 */
export const BuildStatusNotice = ({
  projectId,
  isCompiling,
}: BuildStatusNoticeProps) => {
  const { t } = useTranslation("workbench");
  const summary = useProjectBuildSummary(projectId);
  if (!isCompiling) return null;
  if (summary.stalled > 0) return <StallAlert projectId={projectId} />;
  const text =
    summary.queued === 0
      ? t("documents.buildInProgress")
      : summary.running === 0
        ? t("documents.queueOnly", { count: summary.queued })
        : t("documents.queueSummary", {
            running: summary.running,
            queued: summary.queued,
          });
  return (
    <div
      className="flex items-center gap-1"
      data-testid="build-progress-note"
      data-queued={String(summary.queued)}
      style={{
        margin: "0 0.125rem 0.5rem",
        fontSize: "0.65625rem",
        lineHeight: 1.4,
        color: "var(--fg-3)",
      }}
    >
      <RefreshCw
        size="0.5625rem"
        className="spin"
        style={{ flexShrink: 0 }}
      />
      <span style={{ minWidth: 0, overflowWrap: "anywhere" }}>{text}</span>
    </div>
  );
};
