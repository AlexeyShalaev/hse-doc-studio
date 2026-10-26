import { useTranslation } from "react-i18next";
import { RemoteConnectionCard } from "@features/git-remote";
import { SectionCard } from "../SectionCard";

export type SyncRemoteSectionProps = {
  projectId: string;
};

export const SyncRemoteSection = ({ projectId }: SyncRemoteSectionProps) => {
  const { t } = useTranslation("workspace");
  return (
    <SectionCard title={t("projectSettings.sectionSyncRemote")} fullSpan>
      <RemoteConnectionCard projectId={projectId} />
    </SectionCard>
  );
};
