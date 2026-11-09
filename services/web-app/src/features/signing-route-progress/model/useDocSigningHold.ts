import { useQueries } from "@tanstack/react-query";
import { useBootstrap } from "@entities/session";
import {
  isRouteLive,
  signingRouteApi,
  signingRouteKeys,
  useSigningRoutes,
} from "@entities/signing-route";

/** Документ держит идущий маршрут: какой, по какой точке и на каком шаге. */
export type SigningHold = {
  routeId: string;
  profileId: string;
  step: number | null;
  total: number;
};

/**
 * Идёт ли маршрут подписания, в который входит документ (docs/design/signing-route.md, 5.5).
 * Пока идёт, подписи документа менять нельзя, а пересборка остановит маршрут. Сводка маршрутов
 * проекта не называет документы, поэтому состав берём из хода каждого идущего маршрута: их
 * единицы, а состав идущего маршрута не меняется. Маршруты есть только на сервере.
 */
export const useDocSigningHold = (
  projectId: string,
  docId: string,
): SigningHold | null => {
  const boot = useBootstrap().data;
  const enabled = boot?.mode === "server" && docId !== "";
  const { data } = useSigningRoutes(projectId, null, { enabled });
  const live = enabled
    ? (data?.items ?? []).filter((r) => isRouteLive(r.status))
    : [];
  const details = useQueries({
    queries: live.map((summary) => ({
      queryKey: signingRouteKeys.route(projectId, summary.id),
      queryFn: ({ signal }: { signal: AbortSignal }) =>
        signingRouteApi.get(projectId, summary.id, signal),
      staleTime: 60_000,
      retry: false,
    })),
  });
  const index = details.findIndex(
    (query) => query.data?.docs.some((doc) => doc.doc_id === docId) === true,
  );
  const summary = index === -1 ? undefined : live[index];
  if (!summary) return null;
  return {
    routeId: summary.id,
    profileId: summary.profile.id,
    step: summary.current_step,
    total: summary.steps_total,
  };
};
