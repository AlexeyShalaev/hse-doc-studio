import { useTranslation } from "react-i18next";
import { summarize } from "../../lib/summary";
import { useOutcomeModel } from "../../model";
import { SectionShell, SectionStub } from "./SectionShell";

/** Документы и итоговые имена файлов. Содержимое: срез F3. */
export const DocumentsSection = () => {
  const { t } = useTranslation("packOutcome");
  const { shown } = useOutcomeModel();
  const sum = shown ? summarize(shown) : null;
  return (
    <SectionShell
      id="documents"
      title={t("sections.documents")}
      count={
        sum
          ? t("sections.count.documents", {
              active: sum.documentsActive,
              total: sum.documentsTotal,
            })
          : null
      }
      loading={!shown}
    >
      <SectionStub />
    </SectionShell>
  );
};
