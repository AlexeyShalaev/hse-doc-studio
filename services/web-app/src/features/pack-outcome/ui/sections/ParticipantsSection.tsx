import { useTranslation } from "react-i18next";
import { summarize } from "../../lib/summary";
import { useOutcomeModel } from "../../model";
import { SectionShell, SectionStub } from "./SectionShell";

/** Автор или авторы и руководители, в том числе отсутствующие. Содержимое: срез F3. */
export const ParticipantsSection = () => {
  const { t } = useTranslation("packOutcome");
  const { shown } = useOutcomeModel();
  const sum = shown ? summarize(shown) : null;
  return (
    <SectionShell
      id="participants"
      title={t("sections.participants")}
      count={
        sum
          ? t("sections.count.participants", {
              present: sum.participantsPresent,
              total: sum.participantsTotal,
            })
          : null
      }
      loading={!shown}
    >
      <SectionStub />
    </SectionShell>
  );
};
