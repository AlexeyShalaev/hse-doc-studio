import { useTranslation } from "react-i18next";
import { AlertTriangle, Ban, RefreshCw } from "lucide-react";
import { PRE_LAUNCH_CODES, isInterrupted } from "@entities/compile";
import type { CompileError } from "@entities/document";

export type CompileFailureNoticeProps = {
  /** Причина от сервера; null у записей старых версий, где причина не сохранялась. */
  error: CompileError | null;
  /** Сборка упала или её отменили (в том числе прервал перезапуск сервера: код `interrupted`). */
  status: "failure" | "cancelled";
  /** Есть ли в журнале вывод самой сборки (не только служебные строки). */
  hasOutput: boolean;
  onRetry?: () => void;
  retryDisabled?: boolean;
};

/**
 * Плашка над журналом упавшей сборки: код и человеческий текст «что делать». Если вывода сборки нет
 * (LaTeX не запускался или раннер не прислал ни строки), так и написано, с причиной из кода.
 */
export const CompileFailureNotice = ({
  error,
  status,
  hasOutput,
  onRetry,
  retryDisabled = false,
}: CompileFailureNoticeProps) => {
  const { t } = useTranslation("documents");
  const cancelled = status === "cancelled";
  const interrupted = isInterrupted(status, error?.code);
  const color = cancelled ? "var(--fg-2)" : "var(--c-err)";
  const Icon = cancelled ? Ban : AlertTriangle;
  const preLaunch = error !== null && PRE_LAUNCH_CODES.has(error.code);

  return (
    <div
      role="alert"
      data-testid="compile-failure"
      data-code={error?.code ?? "unknown"}
      className="flex items-start gap-3"
      style={{
        padding: "12px 16px",
        background: "var(--bg-1)",
        borderBottom: `1px solid ${color}`,
        borderLeft: `3px solid ${color}`,
      }}
    >
      <Icon size={18} style={{ color, flexShrink: 0, marginTop: 1 }} />
      <div className="flex flex-col" style={{ gap: 3, minWidth: 0, flex: 1 }}>
        <strong style={{ fontSize: "0.8125rem" }}>
          {interrupted
            ? t("compile.failure.interruptedTitle")
            : cancelled
              ? t("compile.failure.cancelledTitle")
              : t("compile.failure.title")}
          {error && (
            <span
              className="mono"
              data-testid="compile-failure-code"
              style={{
                marginLeft: 8,
                fontSize: "0.6875rem",
                fontWeight: 400,
                color: "var(--fg-3)",
              }}
            >
              {error.code}
            </span>
          )}
        </strong>
        <span
          data-testid="compile-failure-message"
          style={{ fontSize: "0.75rem", color: "var(--fg-2)", lineHeight: 1.5 }}
        >
          {error ? error.message : t("compile.failure.unknownReason")}
        </span>
        {error?.detail && (
          <span
            className="mono"
            data-testid="compile-failure-detail"
            style={{
              fontSize: "0.6875rem",
              color: "var(--fg-3)",
              whiteSpace: "pre-wrap",
              overflowWrap: "anywhere",
            }}
          >
            {error.detail}
          </span>
        )}
        {!hasOutput && !interrupted && (
          <span
            data-testid="compile-failure-no-output"
            style={{
              fontSize: "0.7188rem",
              color: "var(--fg-2)",
              lineHeight: 1.5,
            }}
          >
            {preLaunch
              ? t("compile.failure.noOutputNotStarted")
              : t("compile.failure.noOutputEmpty")}
          </span>
        )}
      </div>
      {onRetry && (
        <button
          type="button"
          className="btn xs"
          onClick={onRetry}
          disabled={retryDisabled}
          style={{ flexShrink: 0 }}
        >
          <RefreshCw size={11} />
          {t("compile.failure.retry")}
        </button>
      )}
    </div>
  );
};
