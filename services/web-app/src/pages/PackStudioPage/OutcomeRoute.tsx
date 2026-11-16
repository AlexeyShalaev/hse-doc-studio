import { lazy, Suspense } from "react";
import { ArrowLeft } from "lucide-react";
import { Link, Navigate, useLocation, useParams } from "react-router";
import { useTranslation } from "react-i18next";
import {
  PACK_STUDIO_PATH,
  packErrorText,
  packFilesPath,
  packOutcomePath,
  usePackTree,
  usePackWorkspace,
} from "@entities/pack-studio";
import {
  WorkspaceStateBadge,
  workspaceSource,
} from "@features/pack-workspaces";
import { loadPackOutcomeNamespace } from "@shared/lib/i18n/packOutcomeNamespace";
import { EmptyState, ErrorState, Spinner } from "@shared/ui";
import { NotReady } from "./NotReady";

// Экран «Результат»: свой чанк (features/pack-outcome) и свой словарь, грузятся с первым входом.
const OutcomeScreen = lazy(() =>
  Promise.all([
    import("@features/pack-outcome"),
    loadPackOutcomeNamespace(),
  ]).then(([m]) => ({ default: m.OutcomeScreen })),
);

const Loading = () => (
  <div
    className="ps-page flex justify-center"
    data-testid="outcome-route-loading"
  >
    <Spinner size="lg" />
  </div>
);

/**
 * Экран «Результат» версии: `/pack-studio/w/<пространство>/result/<пак>/<шаблон>/<версия>`.
 * Шапка пространства и состояние «клонируется» те же, что у режима «Файлы», дальше всё делает
 * сам экран (features/pack-outcome): состояние в query адреса, данные из хуков контракта.
 */
export const OutcomeRoute = () => {
  const { t } = useTranslation("packStudio");
  const {
    workspaceId = "",
    pack = "",
    template = "",
    version = "",
  } = useParams<{
    workspaceId: string;
    pack: string;
    template: string;
    version: string;
  }>();
  const workspace = usePackWorkspace(workspaceId);

  if (workspace.isPending) return <Loading />;
  if (workspace.isError) {
    return (
      <div className="ps-page">
        <ErrorState
          framed
          description={packErrorText(workspace.error)}
          onRetry={() => void workspace.refetch()}
        />
        <Link to={PACK_STUDIO_PATH} className="ps-link">
          {t("workspace.back")}
        </Link>
      </div>
    );
  }
  const ws = workspace.data;
  return (
    <div className="ps-workspace" data-testid="ps-outcome">
      <header className="ps-ws-head">
        <Link
          to={PACK_STUDIO_PATH}
          className="icon-btn"
          aria-label={t("workspace.back")}
          title={t("workspace.back")}
          data-testid="ws-back"
        >
          <ArrowLeft size="0.9375rem" />
        </Link>
        <div className="ps-ws-head-text">
          <div className="ps-ws-title">
            <h1 className="ps-ws-name truncate">{ws.label}</h1>
            <WorkspaceStateBadge workspace={ws} />
          </div>
          <div className="ps-ws-meta mono truncate" title={workspaceSource(ws)}>
            {workspaceSource(ws)}
          </div>
        </div>
        <div className="ps-ws-head-actions">
          <Link
            to={packFilesPath(ws.id)}
            className="btn sm"
            data-testid="ws-files-link"
          >
            {t("tree.title")}
          </Link>
        </div>
      </header>
      {ws.state !== "ready" ? (
        <div className="ps-page">
          <NotReady workspace={ws} />
        </div>
      ) : (
        <Suspense fallback={<Loading />}>
          <OutcomeScreen workspace={ws} version={{ pack, template, version }} />
        </Suspense>
      )}
    </div>
  );
};

/**
 * Вход без версии (`/result`) и корень пространства: открывает версию по умолчанию первого
 * шаблона, сохраняя query. Нет версий: подсказка и переход в режим «Файлы».
 */
export const OutcomeEntry = () => {
  const { t } = useTranslation("packStudio");
  const { workspaceId = "" } = useParams<{ workspaceId: string }>();
  const { search } = useLocation();
  const workspace = usePackWorkspace(workspaceId);
  const ready = workspace.data?.state === "ready";
  const tree = usePackTree(workspaceId, ready);

  if (workspace.isPending || (ready && tree.isPending)) return <Loading />;
  if (workspace.isError || tree.isError) {
    return <OutcomeRoute />;
  }
  if (!ready) return <OutcomeRoute />;
  for (const pack of tree.data?.packs ?? []) {
    for (const template of pack.templates) {
      const chosen =
        template.versions.find((v) => v.version === template.default_version) ??
        template.versions[template.versions.length - 1];
      if (chosen) {
        return (
          <Navigate
            to={packOutcomePath(
              workspaceId,
              { pack: pack.id, template: template.id, version: chosen.version },
              search,
            )}
            replace
          />
        );
      }
    }
  }
  return (
    <div className="ps-page">
      <EmptyState
        framed
        title={t("workspace.noVersionsTitle")}
        description={t("workspace.noVersionsLead")}
        action={
          <Link className="btn sm" to={packFilesPath(workspaceId)}>
            {t("workspace.openFiles")}
          </Link>
        }
        testId="outcome-no-versions"
      />
    </div>
  );
};
