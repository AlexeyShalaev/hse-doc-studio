import { useTranslation } from "react-i18next";
import { ProjectBuildsCard } from "@features/build-states";
import { SectionCard } from "../SectionCard";

export type BuildsSectionProps = {
  projectId: string;
};

/** Где идут сборки серверного проекта: личные раннеры владельца или общие. */
export const BuildsSection = ({ projectId }: BuildsSectionProps) => {
  const { t } = useTranslation("workspace");
  return (
    <SectionCard title={t("projectSettings.sectionBuilds")} fullSpan>
      <ProjectBuildsCard projectId={projectId} />
    </SectionCard>
  );
};
