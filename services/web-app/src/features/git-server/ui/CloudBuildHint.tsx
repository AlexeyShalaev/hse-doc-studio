import { ExternalLink, CloudOff } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useGitServers } from "@entities/git-server";
import { useSyncStatus } from "@entities/git-sync";
import { localFromCloudDocsUrl } from "@entities/local-studio";
import { useCapabilities } from "@entities/session";

export type CloudBuildHintProps = { projectId: string };

/**
 * Подсказка в панели сборки: Студия вошла на сервер, а этот проект к облаку не подключён, поэтому
 * собранный PDF останется на компьютере. Переноса проекта в облако одним действием пока нет
 * (сервер принимает только проекты, созданные на нём), поэтому вместо кнопки ссылка на документацию.
 */
export const CloudBuildHint = ({ projectId }: CloudBuildHintProps) => {
  const { t, i18n } = useTranslation("localStudio");
  const { has } = useCapabilities();
  const local = has("git_server_login");
  const servers = useGitServers(local);
  const status = useSyncStatus(local ? projectId : "");
  const signedIn = servers.data?.items.some((s) => s.state === "ok") ?? false;
  if (!local || !signedIn || !status.data) return null;
  if (status.data.pdf_upload.available) return null;
  return (
    <div
      className="flex items-center"
      role="status"
      data-testid="cloud-build-hint"
      style={{
        gap: 8,
        padding: "8px 16px",
        fontSize: 11.5,
        lineHeight: 1.5,
        borderBottom: "1px solid var(--border)",
        background: "var(--bg-1)",
        color: "var(--fg-2)",
      }}
    >
      <CloudOff size={13} aria-hidden="true" style={{ flexShrink: 0 }} />
      <span style={{ flex: 1, minWidth: 0 }}>
        {t("cloud.build.notConnected")}
      </span>
      <a
        href={localFromCloudDocsUrl(i18n.language)}
        target="_blank"
        rel="noreferrer noopener"
        className="flex items-center"
        style={{ gap: 4, flexShrink: 0 }}
        data-testid="cloud-build-hint-docs"
      >
        <ExternalLink size={11} aria-hidden="true" />
        {t("cloud.build.docs")}
      </a>
    </div>
  );
};
