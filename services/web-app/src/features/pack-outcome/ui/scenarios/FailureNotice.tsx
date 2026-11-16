import { useTranslation } from "react-i18next";
import { packErrorText } from "@entities/pack-studio";
import { retryable, type ScenarioFailure } from "../../lib/scenarios";
import { Notice } from "../Notice";

type FailureNoticeProps = {
  failure: ScenarioFailure;
  /** Повторить то же действие (сеть, сбой сервера, занятый вычислитель). */
  onRetry: () => void;
  /** Перечитать файл с диска: чужая правка (`stale_file`) или файла уже нет. */
  onRefresh: () => void;
  /** Записать поверх чужой правки (ETag с диска берёт вызывающий). */
  onOverwrite?: (() => void) | undefined;
  testId?: string;
};

/**
 * Отказ записи или удаления сценария человеческими словами и с действием: «файл изменён,
 * обновите» мягкая плашка, а не ошибка; сеть и сбой сервера лечатся повтором.
 */
export const FailureNotice = ({
  failure,
  onRetry,
  onRefresh,
  onOverwrite,
  testId = "scenario-failure",
}: FailureNoticeProps) => {
  const { t } = useTranslation("packOutcome");
  if (failure.kind === "stale" || failure.kind === "missing") {
    return (
      <Notice
        tone="info"
        title={t(
          failure.kind === "stale"
            ? "scenarios.failure.staleTitle"
            : "scenarios.failure.missingTitle",
        )}
        testId={testId}
        actions={
          <>
            <button
              type="button"
              className="btn sm primary"
              data-testid="scenario-failure-refresh"
              onClick={onRefresh}
            >
              {t("scenarios.failure.refresh")}
            </button>
            {failure.kind === "stale" && onOverwrite && (
              <button
                type="button"
                className="btn sm"
                data-testid="scenario-failure-overwrite"
                onClick={onOverwrite}
              >
                {t("scenarios.failure.overwrite")}
              </button>
            )}
          </>
        }
      >
        {t(
          failure.kind === "stale"
            ? "scenarios.failure.staleLead"
            : "scenarios.failure.missingLead",
        )}
      </Notice>
    );
  }
  const text =
    failure.kind === "invalid"
      ? t("scenarios.failure.invalid", { reason: failure.reason })
      : failure.kind === "taken"
        ? t("scenarios.failure.taken")
        : failure.kind === "offline"
          ? t("scenarios.failure.offline")
          : failure.kind === "server"
            ? t("scenarios.failure.server")
            : failure.kind === "busy"
              ? t("scenarios.failure.busy")
              : packErrorText(failure.error);
  return (
    <Notice
      tone="error"
      title={t("scenarios.failure.title")}
      testId={testId}
      actions={
        retryable(failure) ? (
          <button
            type="button"
            className="btn sm"
            data-testid="scenario-failure-retry"
            onClick={onRetry}
          >
            {t("status.retry")}
          </button>
        ) : undefined
      }
    >
      {text}
    </Notice>
  );
};
