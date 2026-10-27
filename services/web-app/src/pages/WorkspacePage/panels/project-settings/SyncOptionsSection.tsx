import { useTranslation } from "react-i18next";
import { FetchOptionsCard, SharedFolderCard } from "@features/git-remote";
import { SectionCard } from "../SectionCard";

export type SyncOptionsSectionProps = {
  projectId: string;
};

export const SyncOptionsSection = ({ projectId }: SyncOptionsSectionProps) => {
  const { t } = useTranslation("workspace");
  return (
    <SectionCard title={t("projectSettings.sectionSyncOptions")} fullSpan>
      <FetchOptionsCard projectId={projectId} />
    </SectionCard>
  );
};

export const SyncSharedFolderSection = ({
  projectId,
}: SyncOptionsSectionProps) => {
  const { t } = useTranslation("workspace");
  return (
    <SectionCard title={t("projectSettings.sectionSyncSharedFolder")} fullSpan>
      <SharedFolderCard projectId={projectId} />
    </SectionCard>
  );
};
