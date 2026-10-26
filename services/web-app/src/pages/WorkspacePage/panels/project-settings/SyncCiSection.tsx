import { useTranslation } from "react-i18next";
import { CiCard } from "@features/git-exchange";
import { SectionCard } from "../SectionCard";

export type SyncCiSectionProps = {
  projectId: string;
};

export const SyncCiSection = ({ projectId }: SyncCiSectionProps) => {
  const { t } = useTranslation("workspace");
  return (
    <SectionCard title={t("projectSettings.sectionSyncCi")} fullSpan>
      <CiCard projectId={projectId} />
    </SectionCard>
  );
};
