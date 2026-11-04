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
      className="flex flex-col items-start"
      style={{
        gap: 6,
        padding: "6px 10px",
        margin: "6px 8px",
        borderRadius: 6,
        background: "var(--accent-soft)",
        border: "1px solid var(--accent-line)",
        fontSize: 11.5,
      }}
      data-testid="fetch-all-notice"
    >
      <span>
        {t("builds.fetchableCount", { count: builds.fetchable.length })}
      </span>
      <Button
        size="xs"
        variant="primary"
        disabled={fetchBuild.isPending}
        onClick={() => {
          fetchBuild.run(null);
        }}
        data-testid="fetch-all-builds"
      >
        <Download size={11} />
        {fetchBuild.isPending ? t("builds.fetching") : t("builds.fetchAll")}
      </Button>
    </div>
  );
};
