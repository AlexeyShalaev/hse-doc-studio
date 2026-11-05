import { Download } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@shared/ui";
import { useDocBuilds } from "../model/useDocBuilds";
import { useFetchBuild } from "../model/useFetchBuild";

/** Над списком документов в локальной Студии: в облаке есть сборки, которых у вас нет; одна кнопка берёт все. */
export const FetchAllNotice = ({ projectId }: { projectId: string }) => {
  const { t } = useTranslation("devices");
  const builds = useDocBuilds(projectId);
  const fetchBuild = useFetchBuild(projectId);
  if (builds.mode !== "local" || builds.fetchable.length === 0) return null;
  return (
    <div
      className="flex flex-col items-stretch"
      style={{
        gap: "0.375rem",
        padding: "0.375rem 0.625rem",
        margin: "0.375rem 0.5rem",
        borderRadius: "0.375rem",
        background: "var(--accent-soft)",
        border: "1px solid var(--accent-line)",
        fontSize: "0.71875rem",
        minWidth: 0,
        overflowWrap: "anywhere",
      }}
      data-testid="fetch-all-notice"
    >
      <span>
        {t("builds.fetchableCount", { count: builds.fetchable.length })}
      </span>
      <Button
        size="xs"
        variant="primary"
        className="wrap-btn"
        disabled={fetchBuild.isPending}
        onClick={() => {
          fetchBuild.run(null);
        }}
        data-testid="fetch-all-builds"
      >
        <Download size="0.6875rem" />
        {fetchBuild.isPending ? t("builds.fetching") : t("builds.fetchAll")}
      </Button>
    </div>
  );
};
