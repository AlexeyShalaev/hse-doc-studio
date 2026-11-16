import { useTranslation } from "react-i18next";
import { summarize } from "../../lib/summary";
import { useOutcomeModel } from "../../model";
import { SectionShell, SectionStub } from "./SectionShell";

/** Точки сдачи и их пункты. Содержимое: срез F4. */
export const PointsSection = () => {
  const { t } = useTranslation("packOutcome");
  const { shown } = useOutcomeModel();
  const sum = shown ? summarize(shown) : null;
  return (
    <SectionShell
      id="points"
      title={t("sections.points")}
      count={sum ? t("sections.count.points", { count: sum.points }) : null}
      loading={!shown}
    >
      <SectionStub />
    </SectionShell>
  );
};
