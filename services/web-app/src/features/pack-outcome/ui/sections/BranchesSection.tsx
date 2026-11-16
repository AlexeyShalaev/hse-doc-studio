import { useTranslation } from "react-i18next";
import { summarize } from "../../lib/summary";
import { useOutcomeModel } from "../../model";
import { SectionShell, SectionStub } from "./SectionShell";

/** Что станет, если студент выберет иначе (по запросу `include`). Содержимое: срез F5. */
export const BranchesSection = () => {
  const { t } = useTranslation("packOutcome");
  const { shown } = useOutcomeModel();
  const sum = shown ? summarize(shown) : null;
  return (
    <SectionShell
      id="branches"
      title={t("sections.branches")}
      count={
        !sum
          ? null
          : sum.branches === null
            ? t("sections.notRequested")
            : t("sections.count.branches", { count: sum.branches })
      }
      loading={!shown}
    >
      <SectionStub />
    </SectionShell>
  );
};
