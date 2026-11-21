import { useTranslation } from "react-i18next";
import {
  classifyOutcomeFailure,
  packErrorText,
  type OutcomeFailure,
} from "@entities/pack-studio";
import type { ReactNode } from "react";

type Kind = "issues" | "cases" | "map";

const mib = (bytes: number): string =>
  (bytes / 1024 / 1024).toLocaleString(undefined, { maximumFractionDigits: 1 });

/**
 * Отказ расчёта одним блоком: что случилось человеческими словами и одно действие «Повторить»
 * (плюс подсказка по виду отказа через `extra`). Числа и причины берутся из тела ответа.
 */
export const CheckFailure = ({
  kind,
  error,
  onRetry,
  extra,
  noRetry = false,
}: {
  kind: Kind;
  error: unknown;
  onRetry: () => void;
  extra?: Partial<Record<OutcomeFailure["kind"], ReactNode>>;
  noRetry?: boolean;
}) => {
  const { t } = useTranslation("packSpace");
  const failure = classifyOutcomeFailure(error);
  const [title, lead] = ((): [string, string] => {
    switch (failure.kind) {
      case "busy":
        return [
          t("check.failure.busyTitle"),
          t("check.failure.busyLead", { seconds: failure.retryAfterS }),
        ];
      case "rate_limited":
        return [
          t("check.failure.rateTitle"),
          t("check.failure.rateLead", { seconds: failure.retryAfterS }),
        ];
      case "atlas_too_large":
        return [
          t("check.failure.tooManyTitle"),
          t("check.failure.tooManyLead"),
        ];
      case "outcome_too_large":
        return [
          t("check.failure.tooLargeTitle"),
          failure.size !== null && failure.limit !== null
            ? t("check.failure.tooLargeLead", {
                size: mib(failure.size),
                limit: mib(failure.limit),
              })
            : t("check.failure.tooLargeLeadPlain"),
        ];
      case "diff_base_unavailable":
        return [
          t("check.failure.noBaseTitle"),
          t(`check.failure.noBase.${failure.reason ?? "unknown"}`),
        ];
      case "inputs_invalid":
        return [
          t("check.failure.conditionsTitle"),
          failure.field !== null && failure.value !== null
            ? t("check.failure.conditionsLead", {
                field: failure.field,
                value: failure.value,
              })
            : packErrorText(error),
        ];
      default:
        return [t(`check.failure.${kind}Failed`), packErrorText(error)];
    }
  })();
  return (
    <div className="sp-ck-notice" data-tone="error" role="alert">
      <p className="sp-ck-notice-title">{title}</p>
      <p>{lead}</p>
      <div className="sp-ck-actions">
        {extra?.[failure.kind]}
        {noRetry ? null : (
          <button type="button" className="btn sm" onClick={onRetry}>
            {t("check.retry")}
          </button>
        )}
      </div>
    </div>
  );
};
