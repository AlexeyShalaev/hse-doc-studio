import { useCallback } from "react";
import { Navigate, useNavigate, useSearchParams } from "react-router";
import { useTranslation } from "react-i18next";
import { ConnectServerFlow } from "@features/server-connect";
import { localStudioPath, readConnectTarget } from "@entities/local-studio";
import { useCapabilities } from "@entities/session";
import { AppStatusBar } from "@widgets/AppStatusBar";
import { AppTitlebar } from "@widgets/AppTitlebar";

/**
 * /connect?server=…&project=…: локальная Студия подключается к серверу Студии.
 * Сюда ведут кнопка облака «Подключить локальную Студию» и установщик с
 * HSE_STUDIO_CONNECT. На сервере этот адрес ведёт на «Локальную версию».
 */
export const ConnectServerPage = () => {
  const { t } = useTranslation("appChrome");
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const { lacks } = useCapabilities();
  const target = readConnectTarget(params);
  const go = useCallback(
    (path: string) => {
      void navigate(path);
    },
    [navigate],
  );
  if (lacks("git_server_login")) {
    return <Navigate to={localStudioPath(target.projectId)} replace />;
  }
  return (
    <div className="flex flex-col flex-1 bg-bg-0" style={{ minHeight: 0 }}>
      <AppTitlebar />
      <div
        className="flex flex-1 justify-center"
        style={{ overflowY: "auto", minHeight: 0 }}
      >
        <ConnectServerFlow
          target={target}
          clientName={t("wizardPage.studioDeviceName")}
          onNavigate={go}
        />
      </div>
      <AppStatusBar />
    </div>
  );
};
