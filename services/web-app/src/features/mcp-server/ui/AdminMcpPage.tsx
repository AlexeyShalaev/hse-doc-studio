import { useTranslation } from "react-i18next";
import { PageHeader } from "@shared/ui";
import { McpSettingsPanel } from "./McpSettingsPanel";

/** Админка облака: MCP-сервер установки (docs/design/mcp.md, раздел 4). */
export const AdminMcpPage = () => {
  const { t } = useTranslation("adminMcp");
  return (
    <>
      <PageHeader title={t("title")} description={t("lead")} />
      <McpSettingsPanel scope="admin" />
    </>
  );
};
