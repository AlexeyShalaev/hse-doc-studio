import { RotateCcw } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { OutcomeInput } from "@entities/pack-studio";
import { Modal } from "@shared/ui";
import type { SituationModel } from "./useSituationModel";
import { useSituationLabels } from "./useSituationLabels";
import { useAffectsText } from "./useAffectsText";
import { ValuePicker } from "./ValuePicker";

const Row = ({
  input,
  model,
}: {
  input: OutcomeInput;
  model: SituationModel;
}) => {
  const { t } = useTranslation("packSpace");
  const { inputLabel, valueLabel } = useSituationLabels();
  const affects = useAffectsText();
  const value = model.valueOf(input);
  const base = model.baseOf(input);
  const name = inputLabel(input);
  return (
    <div
      className="sp-sit-row"
      data-changed={value !== base ? "true" : undefined}
      data-testid={`sp-sit-row-${input.id}`}
    >
      <div className="sp-sit-row-head">
        <span className="sp-sit-row-label">{name}</span>
        {value !== base ? (
          <button
            type="button"
            className="icon-btn sm"
            aria-label={t("situation.restore", {
              value: valueLabel(input, base),
            })}
            title={t("situation.restore", { value: valueLabel(input, base) })}
            onClick={() => {
              model.setInput(input, base);
            }}
          >
            <RotateCcw size="0.8125rem" aria-hidden="true" />
          </button>
        ) : null}
      </div>
      <ValuePicker
        input={input}
        value={value}
        variant="row"
        onPick={(next) => {
          model.setInput(input, next);
        }}
      />
      <p className="sp-sit-pop-note">{affects(input)}</p>
    </div>
  );
};

/** Окно «Ещё условий»: все остальные; те, что ничего не меняют, в конце отдельным разделом. */
export const MoreDialog = ({
  model,
  onClose,
}: {
  model: SituationModel;
  onClose: () => void;
}) => {
  const { t } = useTranslation("packSpace");
  const { more, inert } = model.groups;
  return (
    <Modal
      isOpen
      onClose={onClose}
      width={560}
      title={t("situation.moreTitle")}
      description={t("situation.moreLead")}
      footer={
        <button type="button" className="btn primary" onClick={onClose}>
          {t("situation.done")}
        </button>
      }
    >
      <div className="sp-sit-dialog" data-testid="sp-sit-more">
        {more.map((input) => (
          <Row key={input.id} input={input} model={model} />
        ))}
        {inert.length > 0 ? (
          <section aria-labelledby="sp-sit-inert-title">
            <h3 className="sp-sit-inert-title" id="sp-sit-inert-title">
              {t("situation.inertTitle")}
            </h3>
            <p className="sp-sit-pop-note">{t("situation.inertLead")}</p>
            {inert.map((input) => (
              <Row key={input.id} input={input} model={model} />
            ))}
          </section>
        ) : null}
      </div>
    </Modal>
  );
};
