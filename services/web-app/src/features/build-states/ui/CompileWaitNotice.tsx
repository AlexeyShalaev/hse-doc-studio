import { useTranslation } from "react-i18next";
import {
  CalendarClock,
  Hourglass,
  Laptop,
  Layers,
  RefreshCw,
  ServerOff,
  Timer,
  type LucideIcon,
} from "lucide-react";
import type { CompileWait } from "@entities/session";
import { hintParts, waitView, type WaitTone } from "../lib/waitView";

const ICONS: Record<CompileWait["reason"], LucideIcon> = {
  queued: Timer,
  quota_wait: Hourglass,
  no_runner: ServerOff,
  runner_lost: RefreshCw,
  superseded: Layers,
  personal_runner: Laptop,
};

const TONE: Record<WaitTone, { fg: string; bg: string; border: string }> = {
  info: {
    fg: "var(--c-info)",
    bg: "var(--bg-1)",
    border: "var(--border)",
  },
  warn: {
    fg: "var(--c-warn)",
    bg: "var(--bg-1)",
    border: "var(--c-warn)",
  },
  err: {
    fg: "var(--c-err)",
    bg: "var(--bg-1)",
    border: "var(--c-err)",
  },
  neutral: {
    fg: "var(--fg-2)",
    bg: "var(--bg-1)",
    border: "var(--border)",
  },
};

export type CompileWaitNoticeProps = {
  wait: CompileWait;
  /** Сборка уже завершилась (итог), а не ждёт: плашка предлагает повторить. */
  finished?: boolean;
  /** Запустить сборку заново. Кнопка видна, когда сборка завершена. */
  onRetry?: () => void;
  retryDisabled?: boolean;
};

/**
 * Плашка над логом сборки: почему сборка пока не идёт и что будет дальше.
 * Очередь, ожидание квоты, нет раннера, раннер потерян (повтор), сборка заменена.
 */
export const CompileWaitNotice = ({
  wait,
  finished = false,
  onRetry,
  retryDisabled = false,
}: CompileWaitNoticeProps) => {
  const { t } = useTranslation("documents");
  const view = waitView(wait);
  const Icon = ICONS[wait.reason];
  const tone = TONE[view.tone];

  const title = (() => {
    if (wait.reason === "queued" || wait.reason === "quota_wait") {
      return wait.queue_position === null
        ? t(`compile.wait.${view.titleKey}NoPlace`)
        : t(`compile.wait.${view.titleKey}`, { position: wait.queue_position });
    }
    if (wait.reason === "runner_lost") {
      return wait.attempt !== null && wait.max_attempts !== null
        ? t("compile.wait.runnerLost", {
            attempt: wait.attempt,
            max: wait.max_attempts,
          })
        : t("compile.wait.runnerLostNoCount");
    }
    return t(`compile.wait.${view.titleKey}`);
  })();

  const hint =
    wait.wait_hint_seconds !== null && view.live
      ? hintParts(wait.wait_hint_seconds)
      : null;

  return (
    <div
      role="status"
      aria-live="polite"
      data-testid={`compile-wait-${wait.reason}`}
      className="flex items-start gap-3"
      style={{
        padding: "12px 16px",
        background: tone.bg,
        borderBottom: `1px solid ${tone.border}`,
        borderLeft: `3px solid ${tone.fg}`,
      }}
    >
      <Icon
        size={18}
        className={wait.reason === "runner_lost" ? "spin" : undefined}
        style={{ color: tone.fg, flexShrink: 0, marginTop: 1 }}
      />
      <div className="flex flex-col" style={{ gap: 3, minWidth: 0, flex: 1 }}>
        <strong style={{ fontSize: 13 }}>{title}</strong>
        <span style={{ fontSize: 12, color: "var(--fg-2)", lineHeight: 1.5 }}>
          {t(`compile.wait.${view.bodyKey}`)}
        </span>
        {hint && (
          <span
            className="flex items-center gap-1 mono"
            style={{ fontSize: 11, color: "var(--fg-3)" }}
          >
            <CalendarClock size={11} />
            {t(
              hint.unit === "s"
                ? "compile.wait.hintSeconds"
                : "compile.wait.hintMinutes",
              { value: hint.value },
            )}
          </span>
        )}
      </div>
      {finished && onRetry && (
        <button
          type="button"
          className="btn xs primary"
          onClick={onRetry}
          disabled={retryDisabled}
          style={{ flexShrink: 0 }}
        >
          <RefreshCw size={11} />
          {wait.reason === "superseded"
            ? t("compile.wait.rebuildSuperseded")
            : t("compile.wait.retry")}
        </button>
      )}
    </div>
  );
};
