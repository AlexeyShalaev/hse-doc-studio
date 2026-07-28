import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { CheckCircle2, RotateCcw, X, XCircle } from "lucide-react";
import {
  usePulls,
  useStartPull,
  useDismissPull,
  useSyncProvider,
  type PullJob,
} from "@entities/ai-runtime";
import { Spinner } from "@shared/ui/Spinner";
import { toast } from "@shared/lib";
import { useInvalidateLocalRuntime } from "../lib/useInvalidateLocalRuntime";

const percentOf = (message: string): number | null => {
  const m = /(\d+)%/.exec(message);
  return m ? Number(m[1]) : null;
};

type DownloadRowProps = {
  job: PullJob;
  onRetry: () => void;
  onDismiss: () => void;
};

const DownloadRow = ({ job, onRetry, onDismiss }: DownloadRowProps) => {
  const { t } = useTranslation("localRuntime");
  const pct = percentOf(job.message);
  return (
    <div
      className="flex flex-col"
      style={{
        gap: 6,
        padding: "8px 12px",
        borderRadius: 6,
        border: "1px solid var(--border)",
        background: "var(--bg-1)",
      }}
    >
      <div className="flex items-center justify-between" style={{ gap: 12 }}>
        <div className="flex items-center" style={{ gap: 8, minWidth: 0 }}>
          {job.state === "running" && <Spinner size="sm" />}
          {job.state === "success" && (
            <CheckCircle2 size={13} style={{ color: "var(--c-ok)" }} />
          )}
          {job.state === "failure" && (
            <XCircle size={13} style={{ color: "var(--c-err)" }} />
          )}
          <span className="mono" style={{ fontSize: 12 }}>
            {job.name}
          </span>
        </div>
        <div className="flex items-center" style={{ gap: 6, flexShrink: 0 }}>
          {job.state === "failure" && (
            <button
              type="button"
              className="btn xs"
              onClick={onRetry}
              title={t("downloads.retryTitle")}
            >
              <RotateCcw size={11} />
              {t("downloads.retry")}
            </button>
          )}
          {job.state !== "running" && (
            <button
              type="button"
              className="icon-btn"
              onClick={onDismiss}
              title={t("downloads.dismissTitle")}
            >
              <X size={12} />
            </button>
          )}
        </div>
      </div>

      <div
        className="dim"
        style={{
          fontSize: 11,
          color: job.state === "failure" ? "var(--c-err)" : "var(--fg-2)",
        }}
      >
        {job.state === "failure" ? (job.error ?? job.message) : job.message}
      </div>

      {job.state === "running" && pct !== null && (
        <div
          style={{
            height: 4,
            borderRadius: 2,
            background: "var(--bg-3)",
            overflow: "hidden",
          }}
        >
          <div
            style={{
              height: "100%",
              width: `${String(pct)}%`,
              background: "var(--accent)",
              transition: "width 0.3s ease",
            }}
          />
        </div>
      )}
    </div>
  );
};

export const DownloadsSection = () => {
  const { t } = useTranslation("localRuntime");
  const pullsQuery = usePulls();
  const startPull = useStartPull();
  const dismissPull = useDismissPull();
  const syncProvider = useSyncProvider();
  const invalidate = useInvalidateLocalRuntime();

  const jobs = pullsQuery.data?.jobs ?? [];
  // Names whose terminal state we've already reacted to (toast + sync), so we
  // fire the side effects once per completion even though we poll repeatedly.
  const ackRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    for (const job of jobs) {
      if (job.state === "running") {
        ackRef.current.delete(job.name); // a re-pull may run again later
        continue;
      }
      if (ackRef.current.has(job.name)) continue;
      ackRef.current.add(job.name);
      if (job.state === "success") {
        toast.success(t("toast.modelLoaded", { name: job.name }));
        syncProvider.mutate(undefined, { onSuccess: invalidate });
      } else {
        toast.error(t("toast.loadFailed", { name: job.name }));
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobs]);

  if (jobs.length === 0) return null;

  return (
    <div className="flex flex-col" style={{ gap: 6 }}>
      <div
        className="dim"
        style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: 0.5 }}
      >
        {t("downloads.heading")}
      </div>
      {jobs.map((job) => (
        <DownloadRow
          key={job.name}
          job={job}
          onRetry={() => {
            startPull.mutate(job.name);
          }}
          onDismiss={() => {
            dismissPull.mutate(job.name);
          }}
        />
      ))}
    </div>
  );
};
