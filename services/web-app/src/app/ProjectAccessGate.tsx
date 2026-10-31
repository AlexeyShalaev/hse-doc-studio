import { useEffect } from "react";
import { Outlet, useParams } from "react-router";
import { useBootstrap, useRefreshSession } from "@entities/session";
import { isProjectUnavailable, useProject } from "@entities/project";
import { ProjectUnavailablePage } from "@pages/ProjectUnavailablePage";
import { useRecentProjectsStore } from "@shared/lib";
import { LinkRevokedScreen } from "@features/guest-session";

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
  const boot = useBootstrap().data;
  const signedIn = boot?.user != null;
  // links: гость по ссылке тоже упирается в 404 (ссылку отозвали или проект чужой).
  const guest = boot?.user == null && boot?.guest != null;
  const unavailable = (signedIn || guest) && isProjectUnavailable(error);
  const refreshSession = useRefreshSession();

  useEffect(() => {
    if (unavailable && projectId !== "") forgetProject(projectId);
  }, [unavailable, projectId, forgetProject]);

  // Гостю 404 значит, что ссылка больше не действует (`link_inactive`): ссылку убираем из его списка.
  useEffect(() => {
    if (guest && unavailable) void refreshSession();
  }, [guest, unavailable, refreshSession]);

  if (guest && unavailable) return <LinkRevokedScreen />;
  return unavailable ? <ProjectUnavailablePage /> : <Outlet />;
};
