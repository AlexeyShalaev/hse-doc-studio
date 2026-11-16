import { useTranslation } from "react-i18next";
import { summarize } from "../../lib/summary";
import { useOutcomeModel } from "../../model";
import { SectionShell, SectionStub } from "./SectionShell";

/** Поля проекта и анкеты с видимостью. Содержимое: срез F3. */
export const MetaSection = () => {
  const { t } = useTranslation("packOutcome");
  const { shown } = useOutcomeModel();
  const sum = shown ? summarize(shown) : null;
  return (
    <SectionShell
      id="meta"
      title={t("sections.meta")}
      count={
        sum
          ? t("sections.count.meta", {
              visible: sum.metaVisible,
              total: sum.metaTotal,
            })
          : null
      }
      loading={!shown}
    >
      <SectionStub />
    </SectionShell>
  );
};
