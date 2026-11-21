import type { ReactNode } from "react";
import { Link, useParams } from "react-router";
import { useTranslation } from "react-i18next";
import {
  PACK_STUDIO_PATH,
  packErrorText,
  usePackTree,
  usePackWorkspace,
  type PackTree,
  type PackWorkspace,
} from "@entities/pack-studio";
import { ErrorState, Spinner } from "@shared/ui";
import { NotReady } from "../NotReady";

/**
 * Пространство и его дерево для маршрутов нового интерфейса: ожидание, ошибка и «не готово»
 * (клон идёт или не удался) решены здесь, дальше только готовое.
 */
export const WithSpaceData = ({
  children,
}: {
  children: (data: { workspace: PackWorkspace; tree: PackTree }) => ReactNode;
}) => {
  const { t } = useTranslation("packStudio");
  const { workspaceId = "" } = useParams<{ workspaceId: string }>();
  const workspace = usePackWorkspace(workspaceId);
  const ready = workspace.data?.state === "ready";
  const tree = usePackTree(workspaceId, ready);

  if (workspace.isPending || (ready && tree.isPending)) {
    return (
      <div className="ps-page flex justify-center" data-testid="space-loading">
        <Spinner size="lg" />
      </div>
    );
  }
  const failure = workspace.isError ? workspace : tree.isError ? tree : null;
  if (failure) {
    return (
      <div className="ps-page">
        <ErrorState
          framed
          description={packErrorText(failure.error)}
          onRetry={() => void failure.refetch()}
        />
        <Link to={PACK_STUDIO_PATH} className="ps-link">
          {t("workspace.back")}
        </Link>
      </div>
    );
  }
  if (!workspace.data || !ready || !tree.data) {
    return (
      <div className="ps-page">
        {workspace.data ? <NotReady workspace={workspace.data} /> : null}
      </div>
    );
  }
  return <>{children({ workspace: workspace.data, tree: tree.data })}</>;
};
