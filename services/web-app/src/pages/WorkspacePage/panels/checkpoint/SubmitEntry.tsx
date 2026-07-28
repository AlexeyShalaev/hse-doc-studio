import { Navigate } from "react-router";
import { useTranslation } from "react-i18next";
import { ClipboardCheck } from "lucide-react";
import type { z } from "zod";
import type { ProjectResponseSchema } from "@entities/project";
import { Spinner } from "@shared/ui/Spinner";
import { useCheckpointReadiness } from "../../lib";
import { PageHead } from "../PageHead";

type Project = z.infer<typeof ProjectResponseSchema>;

export type SubmitEntryProps = {
  project: Project;
};

const PAGE_STYLE = {
  padding: "24px 32px",
  overflowY: "auto",
  flex: 1,
  minHeight: 0,
} as const;

/**
 * Голый /submit без точки. Отдельного экрана упаковки больше нет — сборка живёт
 * на самой контрольной точке, — поэтому адрес ведёт к ближайшей (или
 * закреплённой) точке, а не к общему списку.
 */
export const SubmitEntry = ({ project }: SubmitEntryProps) => {
  const { t } = useTranslation("workbench");
  const { profiles, activeProfile } = useCheckpointReadiness(project.id);

  if (activeProfile != null) {
    return (
      <Navigate
        to={`/projects/${project.id}/submit/cp/${activeProfile.id}`}
        replace
      />
    );
  }

  return (
    <div style={PAGE_STYLE}>
      <PageHead icon={ClipboardCheck} title={t("checkpoint.title")} />
      {profiles.length === 0 ? (
        <p className="dim" style={{ marginTop: 24, fontSize: 13 }}>
          {t("submit.noProfiles")}
        </p>
      ) : (
        <div className="flex justify-center" style={{ padding: 32 }}>
          <Spinner />
        </div>
      )}
    </div>
  );
};
