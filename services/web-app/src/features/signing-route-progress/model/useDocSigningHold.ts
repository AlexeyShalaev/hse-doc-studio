import { useBootstrap } from "@entities/session";
import { useDocSignaturePlan } from "@entities/signature";

/** Документ держит идущий маршрут: какой, по какой точке и на каком шаге. */
export type SigningHold = {
  routeId: string;
  profileId: string;
  step: number | null;
  total: number;
};

/**
 * Идёт ли маршрут подписания, в который входит документ (docs/design/signing-route.md, 5.5).
 * Пока идёт, подписи документа менять нельзя, а пересборка остановит маршрут. Маршрут документа
 * приходит вместе с его планом подписей (`route`, раздел 6.1): сервер считает состояние на
 * текущих файлах, поэтому остановленный пересборкой маршрут плашку уже не держит. Маршруты есть
 * только на сервере и только вошедшему человеку.
 */
export const useDocSigningHold = (
  projectId: string,
  docId: string,
): SigningHold | null => {
  const boot = useBootstrap().data;
  // Гостю по ссылке маршруты закрыты (раздел 7): без входа не спрашиваем.
  const enabled = boot?.mode === "server" && boot.user !== null && docId !== "";
  const { data } = useDocSignaturePlan(projectId, docId, { enabled });
  const route = enabled ? data?.route : null;
  if (route?.status !== "active") return null;
  return {
    routeId: route.id,
    profileId: route.profile_id,
    step: route.current_step,
    total: route.steps_total,
  };
};
