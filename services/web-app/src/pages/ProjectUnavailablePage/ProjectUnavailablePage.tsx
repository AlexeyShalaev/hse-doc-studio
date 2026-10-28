import { useNavigate } from "react-router";
import { AppStatusBar } from "@widgets/AppStatusBar";
import { AppTitlebar } from "@widgets/AppTitlebar";
import { ProjectUnavailableView } from "./ProjectUnavailableView";

/** Страница вместо рабочей области, когда сервер ответил 404 на проект. */
export const ProjectUnavailablePage = () => {
  const navigate = useNavigate();
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
      />
      <AppStatusBar />
    </div>
  );
};
