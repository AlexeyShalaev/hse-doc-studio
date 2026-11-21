import { Check, Info, Minus, TriangleAlert } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { UseQueryResult } from "@tanstack/react-query";
import {
  busyDelaySeconds,
  isOutcomeBusy,
  packErrorText,
  type PackOutcomeExplain,
} from "@entities/pack-studio";
import { Spinner } from "@shared/ui";
import type { Sentence, SentenceTone } from "./explain";

const MARK = {
  ok: Check,
  no: TriangleAlert,
  skip: Minus,
  info: Info,
} as const satisfies Record<SentenceTone, unknown>;

type WhySectionProps = {
  query: UseQueryResult<PackOutcomeExplain>;
  sentences: readonly Sentence[];
  /** Сервер не вернул ни одного решения: от условий студента элемент не зависит или зависит сам. */
  dependsOnInputs: boolean;
};

/**
 * «Почему так»: короткие предложения вместо цепочки правил, у каждого значок исхода
 * (галочка, предупреждение, «не проверялось»). Предложения строит `explainToSentences`.
 */
export const WhySection = ({
  query,
  sentences,
  dependsOnInputs,
}: WhySectionProps) => {
  const { t } = useTranslation("packSpace");
  const refreshing = query.isFetching && query.data !== undefined;
  const busy = isOutcomeBusy(query.error);
  return (
    <section
      className="sp-details-block"
      aria-labelledby="sp-why-title"
      aria-busy={query.isPending || refreshing}
      data-stale={refreshing ? "true" : undefined}
      data-testid="sp-why"
    >
      <h4 className="sp-details-sub" id="sp-why-title">
        {t("details.why.title")}
      </h4>
      {query.isPending && !query.isError && (
        <div className="sp-details-skeleton" aria-hidden="true">
          <div className="shimmer" />
          <div className="shimmer" data-short="true" />
        </div>
      )}
      {query.isError && (
        <div
          className="sp-details-note"
          role="alert"
          data-testid="sp-why-error"
        >
          <p>
            {busy
              ? t("details.why.busy", { count: busyDelaySeconds(query.error) })
              : t("details.why.failed")}
          </p>
          {!busy && (
            <p className="sp-details-muted">{packErrorText(query.error)}</p>
          )}
          <button
            type="button"
            className="btn sm"
            data-testid="sp-why-retry"
            onClick={() => void query.refetch()}
          >
            {t("details.retry")}
          </button>
        </div>
      )}
      {refreshing && (
        <p className="sp-details-muted" role="status">
          <Spinner size="sm" /> {t("details.recalculating")}
        </p>
      )}
      {query.data && sentences.length > 0 && (
        <ul className="sp-why">
          {sentences.map((row) => {
            const Mark = MARK[row.tone];
            return (
              <li
                key={row.id}
                className="sp-why-row"
                data-tone={row.tone}
                data-testid="sp-why-row"
              >
                <span className="sp-why-mark" aria-hidden="true">
                  <Mark size="0.9375rem" />
                </span>
                <p>
                  <span className="sr-only">
                    {t(`details.tone.${row.tone}`)}{" "}
                  </span>
                  {row.facts.map((fact) => (
                    <span key={fact.label} className="sp-why-fact">
                      {fact.label}: <b>{fact.value}</b>.{" "}
                    </span>
                  ))}
                  {row.text}
                </p>
              </li>
            );
          })}
        </ul>
      )}
      {query.data && sentences.length === 0 && (
        <p className="sp-details-muted" data-testid="sp-why-empty">
          {t(
            dependsOnInputs
              ? "details.why.emptyDepends"
              : "details.why.emptyStatic",
          )}
        </p>
      )}
    </section>
  );
};
