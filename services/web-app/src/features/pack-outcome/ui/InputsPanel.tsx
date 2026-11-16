import { useTranslation } from "react-i18next";
import type { OutcomeInput } from "@entities/pack-studio";
import { packErrorText } from "@entities/pack-studio";
import { pickLocalized } from "@shared/lib/i18n/pickLocalized";
import { EmptyState } from "@shared/ui";
import { useOutcomeModel } from "../model";
import { Notice } from "./Notice";

const GROUPS = ["project", "people", "meta", "answers", "variants"] as const;

/**
 * Панель «Вводные». Каркас (срез F1): строится из ответа сервера `inputs`, показывает группы и
 * текущие значения (умолчание версии или отличие из адреса) и сбрасывает отличия. Контролы по
 * типу вводной, «Влияет на», «Не влияют» и набор данных приходят срезом F2.
 */
export const InputsPanel = () => {
  const { t, i18n } = useTranslation("packOutcome");
  const { inputs, url } = useOutcomeModel();
  const overrides = url.state.inputs;
  const changed = Object.keys(overrides).length;

  if (inputs.isPending) {
    return (
      <div
        className="po-skeleton"
        aria-busy="true"
        aria-label={t("loading")}
        data-testid="outcome-inputs-loading"
      >
        <div className="shimmer po-skeleton-row" />
        <div className="shimmer po-skeleton-row" data-short="true" />
        <div className="shimmer po-skeleton-row" />
        <div className="shimmer po-skeleton-row" data-short="true" />
      </div>
    );
  }
  if (inputs.isError) {
    return (
      <Notice
        tone="error"
        title={t("inputs.loadFailed")}
        testId="outcome-inputs-error"
        actions={
          <button
            type="button"
            className="btn sm"
            onClick={() => void inputs.refetch()}
          >
            {t("status.retry")}
          </button>
        }
      >
        {packErrorText(inputs.error)}
      </Notice>
    );
  }
  const list = inputs.data.inputs;
  if (list.length === 0) {
    return (
      <EmptyState
        compact
        title={t("inputs.emptyTitle")}
        description={t("inputs.emptyLead")}
        testId="outcome-inputs-empty"
      />
    );
  }

  const label = (input: OutcomeInput) =>
    pickLocalized(input.label ?? undefined, i18n.language, input.id);
  const valueLabel = (input: OutcomeInput, value: string) =>
    pickLocalized(
      input.values.find((v) => v.value === value)?.label ?? undefined,
      i18n.language,
      value,
    );

  return (
    <div className="po-inputs" data-testid="outcome-inputs">
      <div className="po-inputs-meta">
        <span>{t("inputs.total", { count: list.length })}</span>
        {changed > 0 && (
          <button
            type="button"
            className="po-link"
            data-testid="outcome-inputs-reset"
            onClick={() => {
              url.update({ inputs: {} });
            }}
          >
            {t("inputs.reset")}
          </button>
        )}
      </div>
      {GROUPS.map((group) => {
        const items = list.filter((input) => input.group === group);
        if (items.length === 0) return null;
        return (
          <section
            key={group}
            className="po-inputs-group"
            aria-label={t(`inputs.groups.${group}`)}
          >
            <h3 className="po-inputs-group-title">
              {t(`inputs.groups.${group}`)}
            </h3>
            <dl className="po-inputs-list">
              {items.map((input) => {
                const value = overrides[input.id] ?? input.default;
                return (
                  <div
                    key={input.id}
                    className="po-inputs-row"
                    data-changed={input.id in overrides ? "true" : undefined}
                    data-testid={`outcome-input-${input.id}`}
                  >
                    <dt>{label(input)}</dt>
                    <dd>{valueLabel(input, value)}</dd>
                  </div>
                );
              })}
            </dl>
          </section>
        );
      })}
      <p className="po-stub">{t("inputs.pending")}</p>
    </div>
  );
};
