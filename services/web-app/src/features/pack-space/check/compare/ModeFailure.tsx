import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import {
  classifyOutcomeFailure,
  packErrorText,
  type OutcomeFailure,
} from "@entities/pack-studio";
import { Notice } from "./Notice";

type ModeFailureProps = {
  error: unknown;
  onRetry: () => void;
  /** Какой режим считал: подпись заголовка. */
  mode: "matrix" | "atlas" | "compare" | "lint";
  /** Дополнительные действия по виду отказа (закрепить вводные, выбрать меньше сценариев). */
  extra?: Partial<Record<OutcomeFailure["kind"], ReactNode>>;
  /** Ничего не считалось слишком большим для повтора: кнопка «Повторить» не нужна. */
  noRetry?: readonly OutcomeFailure["kind"][];
};

const mib = (bytes: number): string =>
  (bytes / 1024 / 1024).toLocaleString(undefined, { maximumFractionDigits: 1 });

/**
 * Отказ режима одним блоком: занят сервер, атлас слишком большой, ответ больше предела, нет базы
 * для сравнения, вводные не подходят, версия не читается, сеть, сбой. Тексты у экрана, числа и
 * причины из тела ответа (`limit`, `rows`, `size`, `reason`).
 */
export const ModeFailure = ({
  error,
  onRetry,
  mode,
  extra,
  noRetry = [],
}: ModeFailureProps) => {
  const { t } = useTranslation("packOutcome");
  const failure = classifyOutcomeFailure(error);
  const retry = (
    <button
      type="button"
      className="btn sm"
      data-testid="outcome-mode-retry"
      onClick={onRetry}
    >
      {t("status.retry")}
    </button>
  );
  const actions = (
    <>
      {extra?.[failure.kind]}
      {noRetry.includes(failure.kind) ? null : retry}
    </>
  );
  const common = { tone: "error", actions } as const;

  switch (failure.kind) {
    case "busy":
      return (
        <Notice
          {...common}
          title={t("modes.failure.busyTitle")}
          testId="outcome-mode-busy"
        >
          {t("modes.failure.busyLead", { seconds: failure.retryAfterS })}
        </Notice>
      );
    case "rate_limited":
      return (
        <Notice
          {...common}
          title={t("modes.failure.rateTitle")}
          testId="outcome-mode-rate-limited"
        >
          {t("modes.failure.rateLead", { seconds: failure.retryAfterS })}
        </Notice>
      );
    case "atlas_too_large":
      return (
        <Notice
          {...common}
          title={t("modes.failure.atlasTitle")}
          testId="outcome-mode-atlas-too-large"
        >
          {failure.rows !== null && failure.limit !== null
            ? t("modes.failure.atlasLead", {
                rows: failure.rows,
                limit: failure.limit,
              })
            : t("modes.failure.atlasLeadPlain")}
        </Notice>
      );
    case "outcome_too_large":
      return (
        <Notice
          {...common}
          title={t("modes.failure.tooLargeTitle")}
          testId="outcome-mode-too-large"
        >
          {failure.size !== null && failure.limit !== null
            ? t("modes.failure.tooLargeLead", {
                size: mib(failure.size),
                limit: mib(failure.limit),
              })
            : t("modes.failure.tooLargeLeadPlain")}
        </Notice>
      );
    case "diff_base_unavailable":
      return (
        <Notice
          {...common}
          title={t("modes.failure.noBaseTitle")}
          testId="outcome-mode-no-base"
        >
          {t(`modes.failure.noBase.${failure.reason ?? "unknown"}`)}
        </Notice>
      );
    case "inputs_invalid":
      return (
        <Notice
          {...common}
          title={t("modes.failure.inputsTitle")}
          testId="outcome-mode-inputs-invalid"
        >
          {[
            failure.field !== null && failure.value !== null
              ? t("modes.failure.inputsField", {
                  field: failure.field,
                  value: failure.value,
                })
              : null,
            failure.reason !== null
              ? t("errors.reason", { reason: failure.reason })
              : null,
          ]
            .filter((part) => part !== null)
            .join(" ") || packErrorText(error)}
        </Notice>
      );
    case "unreadable":
      return (
        <Notice
          {...common}
          title={t("errors.title")}
          testId="outcome-mode-unreadable"
        >
          {failure.reason !== null
            ? `${packErrorText(error)} ${t("errors.reason", { reason: failure.reason })}`
            : packErrorText(error)}
        </Notice>
      );
    default:
      return (
        <Notice
          {...common}
          title={t(`modes.failure.${mode}Failed`)}
          testId="outcome-mode-error"
        >
          {packErrorText(error)}
        </Notice>
      );
  }
};
