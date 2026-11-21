import { useTranslation } from "react-i18next";
import type { PackWorkspace } from "@entities/pack-studio";
import { Badge, Spinner } from "@shared/ui";

/**
 * Состояние пространства одной меткой в шапке открытого пространства: подключается,
 * не удалось, обновляется, готово. Список пространств говорит иначе (WorkspaceStatus).
 */
export const WorkspaceStateBadge = ({
  workspace,
}: {
  workspace: PackWorkspace;
}) => {
  const { t } = useTranslation("packStudio");
  if (workspace.state === "cloning") {
    return (
      <Badge variant="info" data-testid="ws-state-cloning">
        <Spinner size="sm" />
        {t("workspaces.state.cloning")}
      </Badge>
    );
  }
  if (workspace.state === "failed") {
    return (
      <Badge variant="error" data-testid="ws-state-failed">
        {t("workspaces.state.failed")}
      </Badge>
    );
  }
  if (workspace.busy) {
    return (
      <Badge variant="info" data-testid="ws-state-fetching">
        <Spinner size="sm" />
        {t("workspaces.state.fetching")}
      </Badge>
    );
  }
  return (
    <Badge variant="success" data-testid="ws-state-ready">
      {t("workspaces.state.ready")}
    </Badge>
  );
};
