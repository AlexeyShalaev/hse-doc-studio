import { useTranslation } from "react-i18next";
import { packErrorText } from "@entities/pack-studio";
import type { PartState, OutcomePart } from "../../lib/part";
import { Notice } from "../Notice";

/** Скелет строк раздела, пока дорогая часть результата ещё не пришла. */
export const RowsSkeleton = ({ testId }: { testId: string }) => (
  <div className="po-skeleton" aria-hidden="true" data-testid={testId}>
    <div className="shimmer po-skeleton-row" />
    <div className="shimmer po-skeleton-row" data-short="true" />
    <div className="shimmer po-skeleton-row" />
  </div>
);

/**
 * Состояние запроса дорогой части: пересчёт (прежние данные на месте, объявляется программой
 * экрана) и ошибка с повтором. Пока данных нет и запрос не упал, ничего не пишет: скелет рисует
 * сам раздел.
 */
export const PartStatus = ({
  state,
  part,
}: {
  state: Pick<
    PartState<OutcomePart>,
    "refreshing" | "failed" | "error" | "retry"
  > & {
    stale: boolean;
  };
  part: OutcomePart;
}) => {
  const { t } = useTranslation("packOutcome");
  return (
    <>
      <p
        className="po-part-status"
        role="status"
        aria-live="polite"
        data-testid={`outcome-${part}-refreshing`}
      >
        {state.refreshing ? t("status.recalculating") : null}
      </p>
      {state.failed && (
        <Notice
          tone="error"
          title={t(state.stale ? "part.failedStale" : "part.failed", {
            name: t(`sections.${part}`),
          })}
          testId={`outcome-${part}-error`}
          actions={
            <button
              type="button"
              className="btn sm"
              data-testid={`outcome-${part}-retry`}
              onClick={state.retry}
            >
              {t("status.retry")}
            </button>
          }
        >
          {packErrorText(state.error)}
        </Notice>
      )}
    </>
  );
};
