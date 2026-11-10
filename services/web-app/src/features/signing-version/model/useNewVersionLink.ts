import { useBootstrap } from "@entities/session";
import { signingCardPath, useSigningRoutes } from "@entities/signing-route";

type ProjectRef = {
  id: string;
  my_role?: string | null | undefined;
};

/**
 * «Отправить новую версию» рядом с расхождением (docs/design/signing-route.md, 12.8): ссылка на
 * карточку «Подписание» маршрута, который снял версию на подписи. Только тому, кто управляет
 * маршрутом (владелец и редактор, раздел 7), и только у идущего или завершённого маршрута: у
 * остановленного и возвращённого карточка и так зовёт отправить снова. Маршруты есть только на
 * сервере; локально и без права ссылки нет (null).
 */
export const useNewVersionLink = (
  project: ProjectRef | undefined,
): ((routeId: string | null | undefined) => string | null) => {
  const boot = useBootstrap().data;
  const isServer = boot?.mode === "server" && boot.user !== null;
  const canManage =
    project?.my_role === "owner" || project?.my_role === "editor";
  // Все маршруты проекта одним запросом: версия могла уйти по маршруту другой точки.
  const list = useSigningRoutes(project?.id ?? "", null, {
    enabled: isServer && canManage && project !== undefined,
  });
  return (routeId) => {
    if (!project || !routeId) return null;
    const route = list.data?.items.find((item) => item.id === routeId);
    if (route?.status !== "active" && route?.status !== "completed")
      return null;
    return signingCardPath(project.id, route.profile.id);
  };
};
