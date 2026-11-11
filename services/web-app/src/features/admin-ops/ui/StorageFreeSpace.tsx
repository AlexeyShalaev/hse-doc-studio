import type { ReactNode } from "react";
import {
  Ban,
  CheckCircle2,
  Circle,
  CircleSlash,
  TriangleAlert,
  XCircle,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { formatFileSize, formatPastTime, localeTag } from "@shared/lib";
import {
  Button,
  ErrorState,
  ProgressBar,
  Spinner,
  TableSkeleton,
} from "@shared/ui";
import type {
  LifecycleSweep,
  LifecycleSweepPreview,
  LifecycleSweepStep,
} from "@entities/session";
import { isSweepActive } from "../api/lifecycleQueries";
import {
  SWEEP_COUNT_CAP,
  excludedByReason,
  isInterruptedStep,
  previewHasCap,
  stepFreedBytes,
  sweepHasMore,
  sweepProgress,
  sweepUnit,
} from "../lib/sweep";
import { Banner } from "./parts";

// «Освободить место» в «Хранилище» (docs/design/storage-cleanup.md, 4.3): предпросмотр по
// источникам, ход по шагам, итог отдельно записями и местом на диске, плашка прошлого прогона.
// Только показ: запросы держат StorageFreeSpaceDialog и Storage.

const num = (n: number): string => n.toLocaleString(localeTag());

/** Название источника из словаря «Хранения данных»; неизвестный ключ показывается как есть. */
const useSourceTitle = () => {
  const { t } = useTranslation("adminStorage");
  return (key: string): string =>
    t(`adminData:lifecycle.source.${key}.title`, { defaultValue: key });
};

// ── предпросмотр ──

type PreviewSource = LifecycleSweepPreview["sources"][number];

const SourceTerm = ({ source }: { source: PreviewSource }) => {
  const { t } = useTranslation("adminStorage");
  if (source.days !== null) {
    return <>{t("storage.free.confirm.older", { days: source.days })}</>;
  }
  // Фиксированный срок: подпись из «Хранения данных» («7 суток после истечения»).
  return (
    <>
      {t(`adminData:lifecycle.fixed.${source.key}`, {
        defaultValue: t("storage.free.confirm.fixed"),
      })}
    </>
  );
};

const SourceCount = ({ source }: { source: PreviewSource }) => {
  const { t } = useTranslation("adminStorage");
  if (source.count === null) return <>{t("storage.free.confirm.unknown")}</>;
  if (source.count === 0) return <>{t("storage.free.confirm.nothingRow")}</>;
  const n = num(source.count);
  if (sweepUnit(source.key) === "files") {
    return (
      <>
        {source.capped
          ? t("storage.free.confirm.filesMore", { n })
          : t("storage.free.confirm.files", { count: source.count, n })}
      </>
    );
  }
  return (
    <>
      {source.capped
        ? t("storage.free.confirm.rowsMore", { n })
        : t("storage.free.confirm.rows", { count: source.count, n })}
    </>
  );
};

export const SweepPreviewList = ({
  preview,
}: {
  preview: LifecycleSweepPreview;
}) => {
  const { t } = useTranslation("adminStorage");
  const title = useSourceTitle();
  return (
    <ul
      className="ops-sweep-list"
      data-testid="sweep-preview"
      aria-label={t("storage.free.confirm.col.source")}
    >
      {preview.sources.map((source) => {
        const empty = source.count === 0;
        return (
          <li
            key={source.key}
            className="ops-sweep-row"
            data-testid={`sweep-source-${source.key}`}
            data-empty={empty ? "" : undefined}
            data-capped={source.capped ? "" : undefined}
          >
            <span className="ops-sweep-name">{title(source.key)}</span>
            <span className="ops-sweep-meta">
              <span className="ops-sweep-term">
                <SourceTerm source={source} />
              </span>
              <span
                className="ops-sweep-count"
                data-unknown={source.count === null ? "" : undefined}
              >
                <SourceCount source={source} />
              </span>
              <span className="ops-sweep-size">
                {source.bytes === null ? "" : formatFileSize(source.bytes)}
              </span>
            </span>
          </li>
        );
      })}
    </ul>
  );
};

const ExcludedList = ({ preview }: { preview: LifecycleSweepPreview }) => {
  const { t } = useTranslation("adminStorage");
  const title = useSourceTitle();
  const groups = excludedByReason(preview);
  if (groups.length === 0) return null;
  return (
    <div className="ops-sweep-excluded" data-testid="sweep-excluded">
      <p className="ops-sweep-excluded-title">
        {t("storage.free.confirm.excluded")}
      </p>
      <ul>
        {groups.map(([reason, keys]) => (
          <li key={reason} data-reason={reason}>
            {t("storage.free.confirm.excludedRow", {
              sources: keys
                .map((key) =>
                  t("storage.free.confirm.sourceQuoted", { name: title(key) }),
                )
                .join(", "),
              reason: t(`storage.free.confirm.reason.${reason}`),
            })}
          </li>
        ))}
      </ul>
    </div>
  );
};

// ── ход и итог ──

const StepIcon = ({ step }: { step: LifecycleSweepStep }) => {
  switch (step.status) {
    case "running":
      return <Spinner size="sm" />;
    case "done":
      return <CheckCircle2 size="0.8125rem" style={{ color: "var(--c-ok)" }} />;
    case "error":
      return isInterruptedStep(step) ? (
        <TriangleAlert size="0.8125rem" style={{ color: "var(--c-warn)" }} />
      ) : (
        <XCircle size="0.8125rem" style={{ color: "var(--c-err)" }} />
      );
    case "skipped":
      return <CircleSlash size="0.8125rem" style={{ color: "var(--fg-3)" }} />;
    default:
      return <Circle size="0.8125rem" style={{ color: "var(--fg-3)" }} />;
  }
};

const StepResult = ({ step }: { step: LifecycleSweepStep }) => {
  const { t } = useTranslation("adminStorage");
  if (step.status === "skipped") return <>{t("storage.free.step.skipped")}</>;
  if (step.status !== "done") return null;
  const freed = stepFreedBytes(step);
  const parts: string[] = [];
  if (step.removed > 0) {
    parts.push(t("storage.free.step.removed", { n: num(step.removed) }));
  }
  if (freed > 0) {
    parts.push(t("storage.free.step.freed", { size: formatFileSize(freed) }));
  }
  if (step.more) parts.push(t("storage.free.step.more"));
  return (
    <>{parts.length > 0 ? parts.join(", ") : t("storage.free.step.nothing")}</>
  );
};

export const SweepSteps = ({ sweep }: { sweep: LifecycleSweep }) => {
  const { t } = useTranslation("adminStorage");
  const title = useSourceTitle();
  return (
    <ul className="ops-sweep-list" data-testid="sweep-steps">
      {sweep.steps.map((step) => (
        <li
          key={step.key}
          className="ops-sweep-row"
          data-testid={`sweep-step-${step.key}`}
          data-status={step.status}
        >
          <span className="ops-sweep-name">
            <span className="ops-sweep-icon">
              <StepIcon step={step} />
            </span>
            <span
              style={{
                color:
                  step.status === "skipped" || step.status === "pending"
                    ? "var(--fg-3)"
                    : undefined,
              }}
            >
              {title(step.key)}
            </span>
          </span>
          <span className="ops-sweep-meta">
            <span className="ops-sweep-result">
              <StepResult step={step} />
            </span>
          </span>
          {step.status === "error" && step.error !== null && (
            <span className="ops-sweep-error">
              {isInterruptedStep(step)
                ? t("storage.free.step.interrupted")
                : step.error}
            </span>
          )}
        </li>
      ))}
    </ul>
  );
};

/** Заголовок прогона: что идёт сейчас или чем закончилось. */
const useSweepTitle = () => {
  const { t } = useTranslation("adminStorage");
  const title = useSourceTitle();
  return (sweep: LifecycleSweep): string => {
    const { n, total, current } = sweepProgress(sweep);
    const totals = {
      count: sweep.removed_total,
      rows: num(sweep.removed_total),
      size: formatFileSize(sweep.freed_bytes),
    };
    switch (sweep.status) {
      case "running":
        return current
          ? t("storage.free.progress", { source: title(current.key), n, total })
          : t("storage.free.starting");
      case "cancelling":
        return t("storage.free.stopping", {
          source: current ? title(current.key) : "",
        });
      case "done":
        return t("storage.free.done", totals);
      case "cancelled":
        return t("storage.free.cancelled", totals);
      case "error":
        return t("storage.free.error", totals);
      case "interrupted":
        return t("storage.free.interrupted");
    }
  };
};

const PhaseIcon = ({ sweep }: { sweep: LifecycleSweep }) => {
  switch (sweep.status) {
    case "running":
    case "cancelling":
      return <Spinner size="sm" />;
    case "done":
      return <CheckCircle2 size="0.875rem" style={{ color: "var(--c-ok)" }} />;
    case "cancelled":
      return <Ban size="0.875rem" style={{ color: "var(--fg-2)" }} />;
    case "error":
      return <XCircle size="0.875rem" style={{ color: "var(--c-err)" }} />;
    case "interrupted":
      return (
        <TriangleAlert size="0.875rem" style={{ color: "var(--c-warn)" }} />
      );
  }
};

/** Ход прогона и его итог: заголовок, полоса, источники с отметками, пояснение S11. */
export const SweepStatus = ({
  sweep,
  now,
  stopping = false,
  onStop,
}: {
  sweep: LifecycleSweep;
  now: number;
  /** Запрос остановки уже ушёл. */
  stopping?: boolean;
  onStop?: (() => void) | undefined;
}) => {
  const { t } = useTranslation("adminStorage");
  const sweepTitle = useSweepTitle();
  const active = isSweepActive(sweep);
  const { n, total } = sweepProgress(sweep);
  // Полоса считает пройденные источники: текущий ещё не закрыт.
  const passed = active ? Math.max(0, n - 1) : n;
  const finished = sweep.status !== "running" && sweep.status !== "cancelling";
  const showNote =
    finished && sweep.status !== "interrupted" && sweep.removed_total > 0;
  return (
    <section
      className="ops-sweep-status"
      data-testid="sweep-status"
      data-status={sweep.status}
      aria-live="polite"
    >
      <div className="ops-sweep-head">
        <span className="ops-sweep-icon">
          <PhaseIcon sweep={sweep} />
        </span>
        <span className="ops-sweep-headtext">
          <span className="ops-sweep-title" data-testid="sweep-title">
            {sweepTitle(sweep)}
          </span>
          <span className="ops-sweep-when">
            {t("storage.free.startedAt", {
              when: formatPastTime(sweep.started_at, now),
            })}
          </span>
        </span>
      </div>
      {active && (
        <ProgressBar
          percent={total > 0 ? (passed / total) * 100 : null}
          label={sweepTitle(sweep)}
        />
      )}
      <SweepSteps sweep={sweep} />
      {finished && sweepHasMore(sweep) && (
        <p className="ops-sweep-note" data-testid="sweep-more">
          {t("storage.free.doneMore")}
        </p>
      )}
      {showNote && (
        <p className="ops-sweep-note" data-testid="sweep-note">
          {t("storage.free.doneNote")}
        </p>
      )}
      {sweep.status === "running" && onStop && (
        <div>
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={stopping}
            onClick={onStop}
            data-testid="sweep-stop"
          >
            {t("storage.free.stop")}
          </Button>
        </div>
      )}
    </section>
  );
};

// ── тело окна ──

export type FreeSpacePreviewState =
  | { status: "loading" }
  | { status: "error"; onRetry?: (() => void) | undefined }
  | { status: "ready"; preview: LifecycleSweepPreview };

export type FreeSpacePanelProps = {
  /**
   * preview: подтверждение по предпросмотру; sweep: ход или итог прогона (после запуска или
   * если прогон уже шёл, когда окно открыли).
   */
  mode: "preview" | "sweep";
  preview: FreeSpacePreviewState;
  sweep: LifecycleSweep | null;
  now: number;
  /** Отказ сервера одной строкой (уже идёт, нет связи). */
  error?: string | null | undefined;
  starting?: boolean | undefined;
  stopping?: boolean | undefined;
  onConfirm: () => void;
  onStop: (id: string) => void;
  onClose: () => void;
};

const Actions = ({ children }: { children: ReactNode }) => (
  <div className="ops-sweep-actions">{children}</div>
);

/** Окно «Освободить место» без рамки: предпросмотр с подтверждением или ход и итог. */
export const FreeSpacePanel = ({
  mode,
  preview,
  sweep,
  now,
  error = null,
  starting = false,
  stopping = false,
  onConfirm,
  onStop,
  onClose,
}: FreeSpacePanelProps) => {
  const { t } = useTranslation("adminStorage");
  const failure = error ? (
    <p className="ops-sweep-failure" role="alert" data-testid="sweep-failure">
      {error}
    </p>
  ) : null;

  if (mode === "sweep") {
    return (
      <div
        className="ops-sweep"
        data-testid="free-space-panel"
        data-mode="sweep"
      >
        {sweep ? (
          <SweepStatus
            sweep={sweep}
            now={now}
            stopping={stopping}
            onStop={() => {
              onStop(sweep.id);
            }}
          />
        ) : (
          <TableSkeleton rows={4} columns={2} />
        )}
        {failure}
        <Actions>
          <Button type="button" variant="ghost" onClick={onClose}>
            {t("storage.free.close")}
          </Button>
        </Actions>
      </div>
    );
  }

  const ready = preview.status === "ready" ? preview.preview : null;
  return (
    <div
      className="ops-sweep"
      data-testid="free-space-panel"
      data-mode="preview"
    >
      <p className="ops-sweep-lead">{t("storage.free.confirm.lead")}</p>
      {preview.status === "loading" && (
        <div data-testid="sweep-preview-loading">
          <TableSkeleton rows={7} columns={3} />
        </div>
      )}
      {preview.status === "error" && (
        <ErrorState
          compact
          description={t("storage.free.confirm.loadFailed")}
          onRetry={preview.onRetry}
          testId="sweep-preview-error"
        />
      )}
      {ready && (
        <>
          <SweepPreviewList preview={ready} />
          {previewHasCap(ready) && (
            <p className="ops-sweep-note" data-testid="sweep-capped">
              {t("storage.free.confirm.capped", { n: num(SWEEP_COUNT_CAP) })}
            </p>
          )}
          {ready.nothing && (
            <p className="ops-sweep-nothing" data-testid="sweep-nothing">
              {t("storage.free.confirm.nothing")}
            </p>
          )}
          <ExcludedList preview={ready} />
        </>
      )}
      <p className="ops-sweep-note">{t("storage.free.confirm.terms")}</p>
      {failure}
      <Actions>
        <Button type="button" variant="ghost" onClick={onClose}>
          {t("storage.free.confirm.cancel")}
        </Button>
        <Button
          type="button"
          disabled={ready === null || ready.nothing || starting}
          onClick={onConfirm}
          data-testid="sweep-confirm"
        >
          {t("storage.free.action")}
        </Button>
      </Actions>
    </div>
  );
};

// ── плашка под шапкой ──

const BANNER_TONE = {
  running: "info",
  cancelling: "info",
  done: "info",
  cancelled: "info",
  error: "warning",
  interrupted: "warning",
} as const;

/** Ход идущего прогона или итог прошлого под шапкой «Хранилища». */
export const SweepBanner = ({
  sweep,
  now,
  onDetails,
  onHide,
}: {
  sweep: LifecycleSweep;
  now: number;
  onDetails: () => void;
  /** Скрыть итог закрытого прогона; у идущего крестика нет. */
  onHide?: (() => void) | undefined;
}) => {
  const { t } = useTranslation("adminStorage");
  const sweepTitle = useSweepTitle();
  const active = isSweepActive(sweep);
  return (
    <div
      className="ops-sweep-banner"
      data-testid="sweep-banner"
      data-status={sweep.status}
    >
      <Banner
        tone={BANNER_TONE[sweep.status]}
        title={sweepTitle(sweep)}
        action={
          <span className="ops-sweep-banner-actions">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={onDetails}
              data-testid="sweep-banner-details"
            >
              {t("storage.free.banner.details")}
            </Button>
            {!active && onHide && (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={onHide}
                data-testid="sweep-banner-hide"
              >
                {t("storage.free.banner.hide")}
              </Button>
            )}
          </span>
        }
      >
        {t("storage.free.startedAt", {
          when: formatPastTime(sweep.started_at, now),
        })}
      </Banner>
    </div>
  );
};
