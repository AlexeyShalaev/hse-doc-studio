import { useTranslation } from "react-i18next";
import { ExchangeCard } from "@features/git-exchange";
import { SectionCard } from "../SectionCard";

export type SyncExchangeSectionProps = {
  projectId: string;
};

export const SyncExchangeSection = ({
  projectId,
}: SyncExchangeSectionProps) => {
  const { t } = useTranslation("workspace");
  return (
    <SectionCard title={t("projectSettings.sectionSyncExchange")} fullSpan>
      <ExchangeCard projectId={projectId} />
    </SectionCard>
  );
};
