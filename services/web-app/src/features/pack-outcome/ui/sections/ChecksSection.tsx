import { useTranslation } from "react-i18next";
import { summarize } from "../../lib/summary";
import { useOutcomeModel } from "../../model";
import { SectionShell, SectionStub } from "./SectionShell";

/** Какие правила проверок применимы к комплекту (по запросу `include`). Содержимое: срез F5. */
export const ChecksSection = () => {
  const { t } = useTranslation("packOutcome");
  const { shown } = useOutcomeModel();
  const sum = shown ? summarize(shown) : null;
  return (
    <SectionShell
      id="checks"
      title={t("sections.checks")}
      count={
        !sum
          ? null
          : sum.checksEnabled === null
            ? t("sections.notRequested")
            : t("sections.count.checks", {
                enabled: sum.checksEnabled,
                total: sum.checksTotal,
              })
      }
      loading={!shown}
    >
      <SectionStub />
    </SectionShell>
  );
};
