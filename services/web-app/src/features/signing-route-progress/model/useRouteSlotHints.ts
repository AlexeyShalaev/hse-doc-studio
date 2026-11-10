import { useTranslation } from "react-i18next";
import { useBootstrap } from "@entities/session";
import type { SignaturePlanSchema } from "@entities/signature";
import {
  routePeople,
  routeWaitOf,
  useSigningRoute,
} from "@entities/signing-route";
import type { z } from "zod";
import { awaitsFreeze, routeTally } from "../lib/routeView";
import { useWaitText } from "../lib/useWaitText";

type SignaturePlan = z.infer<typeof SignaturePlanSchema>;

/**
 * Подсказки плана подписей для документов, которые держит идущий маршрут (signing-route.md, 6.1).
 * План говорит «зафиксируйте заново и подпишите», а это делает сам маршрут: вместо этого сказано,
 * что с подписантом слота и когда до него дойдёт. Маршрут точки берётся из плана (`route`), его
 * ход из ответа маршрута; пока он грузится, сказано только, что PDF зафиксирует маршрут. Оттуда же
 * счёт согласований для шапки и статус «согласовано, подпись после фиксации» у слота ЭП.
 */
export const useRouteSlotHints = (
  projectId: string,
  plan: SignaturePlan | undefined,
) => {
  const { t } = useTranslation("signingProgress");
  const boot = useBootstrap().data;
  const waitText = useWaitText();
  const docs = plan?.docs ?? [];
  const heldDocs = new Set(
    docs.filter((doc) => doc.held_by_route).map((doc) => doc.doc_id),
  );
  // Свои неподписанные слоты, которые держит маршрут: подписать их сейчас нельзя.
  const heldMine = docs
    .filter((doc) => doc.held_by_route)
    .flatMap((doc) => doc.slots)
    .some((slot) => slot.is_mine && slot.status !== "signed");
  const planRoute = plan?.route?.status === "active" ? plan.route : null;
  const { data: route } = useSigningRoute(projectId, planRoute?.id ?? "", {
    enabled: planRoute !== null,
  });
  const meId = boot?.user?.id ?? null;
  const wait = route ? routeWaitOf(route, meId) : null;
  const people = route ? routePeople(route, meId) : [];

  /** Подсказка слота, который держит маршрут; null: документ свободен, подсказка плана в силе. */
  const hint = (docId: string, slotId: string): string | null => {
    if (!heldDocs.has(docId)) return null;
    const participantId =
      route?.docs
        .find((doc) => doc.doc_id === docId)
        ?.slots.find((slot) => slot.slot_id === slotId)?.participant_id ?? null;
    const person = people.find((p) => p.id === participantId);
    if (person && wait) return waitText.slot(person, wait) ?? "";
    return t("wait.freezeByRoute");
  };

  /** Слот ЭП согласован и ждёт фиксации PDF: «согласовано, подпись после фиксации». */
  const approvedSlot = (docId: string, slotId: string): boolean =>
    heldDocs.has(docId) && !!route && awaitsFreeze(route, docId, slotId);

  /** Согласования и подписи идущего маршрута для шапки точки; null без идущего маршрута. */
  const tally = route?.status === "active" ? routeTally(route) : null;

  return { heldDocs, heldMine, hint, approvedSlot, tally };
};
