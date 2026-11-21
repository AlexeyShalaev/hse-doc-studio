import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useSituation } from "../context/useSituation";
import { MoreDialog } from "../situation/MoreDialog";
import { topInputs } from "../situation/topInputs";
import { useSituationLabels } from "../situation/useSituationLabels";
import { useSituationModel } from "../situation/useSituationModel";
import type { PreviewBuild } from "./usePreviewBuild";

/** Окно со всеми условиями: то же, что «Ещё условий» над «Результатом», но с главными тоже. */
const ChangeDialog = ({ onClose }: { onClose: () => void }) => {
  const model = useSituationModel();
  const { shown, more, inert } = model.groups;
  const all = {
    ...model,
    groups: { shown: [], more: [...shown, ...more], inert },
  };
  return <MoreDialog model={all} onClose={onClose} />;
};

/**
 * «Для какого студента»: сводка условий, по которым собирается страница, и «Изменить условия».
 * Условий здесь не выбирают: они те же, что на экране «Результат» (адрес), поэтому девяти списков
 * нет (pack-studio-ux.md, 5.4 пункт 4).
 */
export const Conditions = ({ pv }: { pv: PreviewBuild }) => {
  const { t } = useTranslation("packSpace");
  const { inputLabel, valueLabel } = useSituationLabels();
  const situation = useSituation();
  const [open, setOpen] = useState(false);
  const { inputs, values, loaded } = pv.conditions;
  const top = topInputs(inputs, 3);
  const topIds = new Set(top.map((input) => input.id));
  const known = new Set(inputs.map((input) => input.id));
  const hidden = Object.keys(situation.inputs).filter(
    (id) => known.has(id) && !topIds.has(id),
  ).length;
  return (
    <section className="sp-pv-block" data-testid="sp-pv-conditions">
      <h4 className="sp-pv-sub">{t("preview.forStudent")}</h4>
      {!loaded ? (
        <p className="sp-pv-muted">{t("preview.conditionsLoading")}</p>
      ) : top.length === 0 ? (
        <p className="sp-pv-muted" data-testid="sp-pv-no-conditions">
          {t("preview.noConditions")}
        </p>
      ) : (
        <ul className="sp-pv-chips">
          {top.map((input) => (
            <li key={input.id} className="sp-pv-chip">
              <span>{inputLabel(input)}</span>
              <b>{valueLabel(input, values[input.id] ?? input.default)}</b>
            </li>
          ))}
          {hidden > 0 ? (
            <li className="sp-pv-chip" data-more="true">
              {t("preview.moreChanged", { count: hidden })}
            </li>
          ) : null}
        </ul>
      )}
      {loaded && inputs.length > 0 ? (
        <button
          type="button"
          className="btn sm"
          data-testid="sp-pv-change"
          onClick={() => {
            setOpen(true);
          }}
        >
          {t("preview.changeConditions")}
        </button>
      ) : null}
      {open ? (
        <ChangeDialog
          onClose={() => {
            setOpen(false);
          }}
        />
      ) : null}
    </section>
  );
};
