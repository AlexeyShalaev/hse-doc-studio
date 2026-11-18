import { Eye } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useLintActions } from "./context";

type WitnessLineProps = {
  witness: Readonly<Record<string, string>>;
  testId?: string;
};

/**
 * Комбинация-свидетель одной строкой («вид работы: исследование, состав: один») и кнопка «Показать
 * комбинацию». Значения и подписи берутся из вводных версии, сама комбинация приходит с сервера.
 */
export const WitnessLine = ({ witness, testId }: WitnessLineProps) => {
  const { t } = useTranslation("packOutcome");
  const { labeler, showCombination } = useLintActions();
  const text = Object.entries(witness)
    .map(
      ([input, value]) =>
        `${labeler.input(input)}: ${labeler.value(input, value)}`,
    )
    .join("; ");
  return (
    <div className="ln-witness" data-testid={testId}>
      <span className="ln-witness-text">{text}</span>
      <button
        type="button"
        className="btn sm"
        data-testid="outcome-lint-show-combo"
        aria-label={`${t("lint.finding.showCombo")}: ${text}`}
        onClick={() => {
          showCombination(witness);
        }}
      >
        <Eye size="0.8125rem" aria-hidden="true" />
        {t("lint.finding.showCombo")}
      </button>
    </div>
  );
};
