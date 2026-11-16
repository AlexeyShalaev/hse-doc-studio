import { useTranslation } from "react-i18next";
import { summarize } from "../../lib/summary";
import { useOutcomeModel } from "../../model";
import { SectionShell, SectionStub } from "./SectionShell";

/** Маршрут подписания: шаги, пары, пропущенные. Содержимое: срез F4. */
export const RouteSection = () => {
  const { t } = useTranslation("packOutcome");
  const { shown } = useOutcomeModel();
  const sum = shown ? summarize(shown) : null;
  return (
    <SectionShell
      id="route"
      title={t("sections.route")}
      count={sum ? t("sections.count.route", { count: sum.routes }) : null}
      loading={!shown}
    >
      <SectionStub />
    </SectionShell>
  );
};
