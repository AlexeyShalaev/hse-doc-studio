import { useTranslation } from "react-i18next";
import { coveragePercent } from "../../lib/lint";
import { useOutcomeModel } from "../../model";
import { useScenarioUi } from "./context";

type CoverageBriefProps = {
  /** Перед переходом в режим «Проверка» (закрыть выпадающий список). */
  onOpen?: () => void;
};

/**
 * Краткая сводка покрытия правил сценариями в выборе сценария и матрице: процент из прогона
 * сценариев (`run.coverage`, он уже загружен, второго расчёта нет) и ссылка на режим «Проверка».
 * Без прогона или без сценариев сводки нет.
 */
export const CoverageBrief = ({ onOpen }: CoverageBriefProps) => {
  const { t } = useTranslation("packOutcome");
  const { url } = useOutcomeModel();
  const ui = useScenarioUi();
  const coverage = ui?.run?.coverage;
  if (!coverage || url.state.mode === "student") return null;
  const percent = coveragePercent(coverage);
  return (
    <p
      className="po-note po-coverage-brief"
      data-testid="outcome-coverage-brief"
    >
      <span>
        {t("lint.brief.percent", { percent })}
        {coverage.approximate === true
          ? ` (${t("lint.brief.approximate")})`
          : ""}
      </span>{" "}
      <button
        type="button"
        className="po-link"
        data-testid="outcome-coverage-brief-open"
        onClick={() => {
          onOpen?.();
          url.update({ view: "lint" }, true);
        }}
      >
        {t("lint.brief.details")}
      </button>
    </p>
  );
};
