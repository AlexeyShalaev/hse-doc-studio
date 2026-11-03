import { Navigate, useSearchParams } from "react-router";
import { LocalStudioGuide } from "@features/local-studio-guide";
import { CONNECT_SERVER_PATH, isProjectId } from "@entities/local-studio";
import { useBootstrap } from "@entities/session";
import { i18n } from "@shared/lib";
import { AppStatusBar } from "@widgets/AppStatusBar";
import { AppTitlebar } from "@widgets/AppTitlebar";

const DOCS_BASE = "https://alexeyshalaev.github.io/hse-doc-studio";

/** Справка о локальной версии на языке интерфейса. */
const docsUrl = (lang: string): string =>
  lang.startsWith("en")
    ? `${DOCS_BASE}/en/start/local-from-cloud/`
    : `${DOCS_BASE}/start/local-from-cloud/`;

/**
 * /local-studio: «Локальная версия» облачной Студии. В самой локальной Студии
 * этот адрес ведёт на её экран «Подключиться к серверу».
 */
export const LocalStudioPage = () => {
  const [params] = useSearchParams();
  const { data } = useBootstrap();
  if (data?.mode === "local") {
    return <Navigate to={CONNECT_SERVER_PATH} replace />;
  }
  const project = params.get("project") ?? "";
  return (
    <div className="flex flex-col flex-1 bg-bg-0" style={{ minHeight: 0 }}>
      <AppTitlebar />
      <div
        className="flex flex-1 justify-center"
        style={{ overflowY: "auto", minHeight: 0 }}
      >
        <LocalStudioGuide
          projectId={isProjectId(project) ? project : null}
          docsUrl={docsUrl(i18n.language)}
        />
      </div>
      <AppStatusBar />
    </div>
  );
};
