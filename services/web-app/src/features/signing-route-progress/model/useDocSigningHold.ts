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

const HOLDING = new Set(["active", "paused", "returned", "completed"]);

/** Маршрут документа и его версия на подписи: для плашки расхождения в редакторе (12.2). */
export type DocRouteVersion = {
  routeId: string;
  profileId: string;
  status: string;
  /** Когда снята версия на подписи; null, если её нет (сервер до R16, перенос не удался). */
  pinnedAt: string | null;
  /** Рабочая сборка документа ушла от версии на подписи. */
  changed: boolean;
  /** Перенос маршрута 0.20.0 не нашёл отправленную версию: стоит с `sent_changed` (12.11). */
  lost: boolean;
};

/**
 * Версия на подписи документа, который держит маршрут (`HOLDING_STATUSES`: идёт, остановлен,
 * возвращён, завершён). Тот же запрос плана, что у `useDocSigningHold`. «Есть изменения» это
 * `working_differs` документа или он в `changed_docs` маршрута (у маршрута 0.20.0 без версии
 * на подписи план документа версии не знает).
 */
export const useDocRouteVersion = (
  projectId: string,
  docId: string,
): DocRouteVersion | null => {
  const boot = useBootstrap().data;
  const enabled = boot?.mode === "server" && boot.user !== null && docId !== "";
  const { data } = useDocSignaturePlan(projectId, docId, { enabled });
  const route = enabled ? data?.route : null;
  if (!route || !HOLDING.has(route.status)) return null;
  const doc = data?.docs.find((d) => d.doc_id === docId);
  const pinned = doc?.pinned ?? null;
  const changed =
    (doc?.working_differs ?? false) || route.changed_docs.includes(docId);
  return {
    routeId: route.id,
    profileId: route.profile_id,
    status: route.status,
    pinnedAt: pinned?.pinned_at ?? null,
    changed,
    lost:
      changed &&
      pinned === null &&
      route.status === "paused" &&
      route.stop_reason === "sent_changed",
  };
};
