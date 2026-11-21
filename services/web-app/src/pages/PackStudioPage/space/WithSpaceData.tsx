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
import { ApiError } from "@shared/api";
import { EmptyState, ErrorState, Spinner } from "@shared/ui";
import { NotReady } from "../NotReady";

/** Сервер не знает такого пространства (нет записи или адрес не похож на идентификатор). */
const isMissing = (error: unknown): boolean =>
  error instanceof ApiError && (error.status === 404 || error.status === 422);

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
  const { t: tSpace } = useTranslation("packSpace");
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
  if (workspace.isError && isMissing(workspace.error)) {
    return (
      <div className="ps-page">
        <EmptyState
          framed
          title={tSpace("shell.notFound.title")}
          description={tSpace("shell.notFound.lead")}
          action={
            <Link className="btn primary" to={PACK_STUDIO_PATH}>
              {tSpace("shell.notFound.action")}
            </Link>
          }
          testId="space-not-found"
        />
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
