import { ArrowRight, Database, HardDrive, Info } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { formatFileSize, formatPastTime } from "@shared/lib";
import { Button, Section } from "@shared/ui";
import type { RunnerDiskSummary } from "@entities/runner";
import type { ViewStatus } from "../lib/viewStatus";

// Блок «Где ещё освободить место» под карточками «Хранилища» (docs/design/storage-cleanup.md, 4.3
// и S12): ссылка на «Хранение данных», сводка дисков общих раннеров с открытием окна «Диск» и
// честная строка о том, что сюда не входит.

export type StorageMoreSpaceProps = {
  /** Сводка `GET /api/admin/runners/disk-summary`. */
  status: ViewStatus;
  summary: RunnerDiskSummary | null;
  now: number;
  onRetry?: (() => void) | undefined;
  /** Открыть окно «Диск» раннера из сводки. */
  onOpenRunner: (runner: { id: string; name: string }) => void;
};

const RunnersSummary = ({
  status,
  summary,
  now,
  onRetry,
  onOpenRunner,
}: StorageMoreSpaceProps) => {
  const { t } = useTranslation("adminStorage");
  if (status === "loading") {
    return (
      <span className="ops-more-sub" data-testid="more-runners-loading">
        <span className="ops-more-skeleton" aria-hidden="true" />
      </span>
    );
  }
  if (status !== "ready" || summary === null) {
    return (
      <span className="ops-more-sub" data-testid="more-runners-error">
        {t("storage.free.more.runnersFailed")}
        {onRetry && (
          <Button type="button" variant="ghost" size="xs" onClick={onRetry}>
            {t("storage.free.more.retry")}
          </Button>
        )}
      </span>
    );
  }
  if (summary.reporting === 0) {
    return (
      <span className="ops-more-sub" data-testid="more-runners-none">
        {summary.outdated > 0
          ? t("storage.free.more.runnersNone", {
              version: summary.min_version,
            })
          : t("storage.free.more.runnersNoReport")}
      </span>
    );
  }
  return (
    <>
      <span className="ops-more-title" data-testid="more-runners-total">
        {summary.cleanable_bytes > 0
          ? t("storage.free.more.runners", {
              size: formatFileSize(summary.cleanable_bytes),
            })
          : t("storage.free.more.runnersClean")}
      </span>
      {summary.top.length > 0 && (
        <ul className="ops-more-runners" data-testid="more-runners-top">
          {summary.top.map((runner) => (
            <li key={runner.runner_id}>
              <button
                type="button"
                className="ops-link"
                data-testid={`more-runner-${runner.runner_id}`}
                aria-label={t("storage.free.more.runnerOpen", {
                  name: runner.name,
                })}
                onClick={() => {
                  onOpenRunner({ id: runner.runner_id, name: runner.name });
                }}
              >
                {runner.name}
              </button>
              <span className="ops-more-size">
                {formatFileSize(runner.cleanable_bytes)}
              </span>
              <span className="ops-more-when">
                {t("storage.free.more.runnerMeasured", {
                  when: formatPastTime(runner.measured_at, now),
                })}
              </span>
            </li>
          ))}
        </ul>
      )}
      {summary.outdated > 0 && (
        <span className="ops-more-sub" data-testid="more-runners-outdated">
          {t("storage.free.more.outdated", {
            count: summary.outdated,
            n: summary.outdated,
            version: summary.min_version,
          })}
        </span>
      )}
    </>
  );
};

export const StorageMoreSpace = (props: StorageMoreSpaceProps) => {
  const { t } = useTranslation("adminStorage");
  return (
    <Section
      title={t("storage.free.more.title")}
      description={t("storage.free.more.lead")}
      testId="storage-more"
    >
      <ul className="ops-more">
        <li>
          <Database
            size="0.9375rem"
            aria-hidden="true"
            className="ops-more-icon"
          />
          <div className="ops-more-text">
            <Link
              to="/admin/data"
              className="ops-more-link ops-more-title"
              data-testid="more-data"
            >
              {t("storage.free.more.data")}
            </Link>
          </div>
        </li>
        <li data-testid="more-runners">
          <HardDrive
            size="0.9375rem"
            aria-hidden="true"
            className="ops-more-icon"
          />
          <div className="ops-more-text">
            <RunnersSummary {...props} />
            <Link
              to="/admin/runners"
              className="ops-more-link ops-more-all"
              data-testid="more-all-runners"
            >
              {t("storage.free.more.allRunners")}
              <ArrowRight size="0.75rem" aria-hidden="true" />
            </Link>
          </div>
        </li>
        <li data-testid="more-not-included">
          <Info size="0.9375rem" aria-hidden="true" className="ops-more-icon" />
          <p className="ops-more-sub">{t("storage.free.more.notIncluded")}</p>
        </li>
      </ul>
    </Section>
  );
};
