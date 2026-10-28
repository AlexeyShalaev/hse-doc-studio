import { useEffect } from "react";
import { Outlet, useParams } from "react-router";
import { useBootstrap } from "@entities/session";
import { isProjectUnavailable, useProject } from "@entities/project";
import { ProjectUnavailablePage } from "@pages/ProjectUnavailablePage";
import { useRecentProjectsStore } from "@shared/lib";

/**
 * Охранник маршрутов /projects/:projectId/*. Сервер отвечает 404 и на чужой, и
 * на несуществующий проект: вместо пустой рабочей области показываем одну
 * страницу «не найден или нет доступа» и убираем проект из недавних, чтобы
 * мёртвая ссылка не жила в истории. Запрос общий с рабочей областью (тот же
 * ключ), второго обращения к серверу нет.
 */
export const ProjectAccessGate = () => {
  const { projectId = "" } = useParams<{ projectId: string }>();
  const { error } = useProject(projectId);
  const forgetProject = useRecentProjectsStore((s) => s.forgetProject);
  // Доступ к проектам разграничен только у вошедшего человека; в локальном
  // режиме аккаунтов нет и поведение прежнее.
  const signedIn = useBootstrap().data?.user != null;
  const unavailable = signedIn && isProjectUnavailable(error);

  useEffect(() => {
    if (unavailable && projectId !== "") forgetProject(projectId);
  }, [unavailable, projectId, forgetProject]);

  return unavailable ? <ProjectUnavailablePage /> : <Outlet />;
};
