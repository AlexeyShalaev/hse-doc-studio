import { useNavigate, useParams } from "react-router";
import { useBootstrap } from "@entities/session";
import { useRequestAccess } from "@entities/invitation";
import { AppStatusBar } from "@widgets/AppStatusBar";
import { AppTitlebar } from "@widgets/AppTitlebar";
import { ProjectUnavailableView } from "./ProjectUnavailableView";

/** Страница вместо рабочей области, когда сервер ответил 404 на проект. */
export const ProjectUnavailablePage = () => {
  const navigate = useNavigate();
  const { projectId = "" } = useParams<{ projectId: string }>();
  const boot = useBootstrap().data;
  const request = useRequestAccess();
  const signedIn = boot?.mode === "server" && boot.user !== null;
  return (
    <div className="flex flex-col flex-1 bg-bg-0" style={{ minHeight: 0 }}>
      <AppTitlebar />
      <ProjectUnavailableView
        onHome={() => {
          void navigate("/", { replace: true });
        }}
        onBack={() => {
          void navigate(-1);
        }}
        {...(signedIn && projectId !== ""
          ? {
              requestAccess: {
                pending: request.isPending,
                sent: request.isSuccess,
                failed: request.isError,
                onSend: (message: string | null) => {
                  request.mutate({ projectId, message });
                },
              },
            }
          : {})}
      />
      <AppStatusBar />
    </div>
  );
};
