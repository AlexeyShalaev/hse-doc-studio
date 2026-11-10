import {
  routeChangedDocs,
  type RouteDoc,
  type RouteParticipant,
  type SigningRoute,
  type SigningRoutePreview,
} from "@entities/signing-route";

// Версия на подписи в карточке «Подписание» и плашке редактора (docs/design/signing-route.md,
// 12.2, 12.6, 12.9): что подписывают, есть ли изменения после отправки и что изменит новая версия.

export type RouteVersionView = {
  /** Документы, у которых есть версия на подписи или изменения, по порядку маршрута. */
  docs: readonly RouteDoc[];
  /** Документы, рабочая сборка которых ушла от отправленной. */
  changed: readonly RouteDoc[];
  /**
   * Дата версии, которую подписывают: самая поздняя у изменившихся документов, без изменений
   * у всех. null, если версий на подписи нет (сервер до R16, черновик, отмена).
   */
  sentAt: string | null;
  /**
   * Перенос маршрута 0.20.0 не восстановил версию (12.11): маршрут стоит с `sent_changed`, а у
   * документа версии на подписи нет. Карточка пишет «восстановить нельзя: отправьте новую версию».
   */
  lost: boolean;
};

const latest = (dates: readonly string[]): string | null =>
  dates.reduce<string | null>(
    (best, date) =>
      best === null || Date.parse(date) > Date.parse(best) ? date : best,
    null,
  );

export const routeVersionView = (route: SigningRoute): RouteVersionView => {
  const changedIds = new Set(routeChangedDocs(route));
  const changed = route.docs.filter(
    (doc) => changedIds.has(doc.doc_id) || doc.changed === true,
  );
  const docs = route.docs.filter(
    (doc) => (doc.sent ?? null) !== null || changed.includes(doc),
  );
  const dated = changed.some((doc) => doc.sent) ? changed : route.docs;
  return {
    docs,
    changed,
    sentAt: latest(dated.flatMap((doc) => (doc.sent ? [doc.sent.at] : []))),
    // `sent` строго null: поля нет до R16, отсутствие значит «ничего не менялось».
    lost:
      route.status === "paused" &&
      route.stop_reason === "sent_changed" &&
      route.docs.some((doc) => doc.sent === null),
  };
};

export type NewVersionSummary = {
  /** Документы, у которых снимется новая версия (`changed`, а без прежней версии `new`). */
  changed: readonly string[];
  /** Документы без изменений: версия, B и подписи над ним остаются. */
  kept: readonly string[];
  /**
   * Кто согласует заново: согласие было, но не переносится (`keeps_approval` false). Сам
   * отправитель согласует отправкой, ещё не согласовавшие и так согласуют в свою очередь.
   */
  reapprove: readonly RouteParticipant[];
};

/**
 * Следствия «Отправить новую версию» из предпросмотра (12.6). Пока сервер не отдаёт `change` и
 * `keeps_approval` (до R16), изменившиеся документы берутся из маршрута, а людей не перечисляем.
 */
export const newVersionSummary = (
  route: SigningRoute,
  preview: SigningRoutePreview,
  meId: string | null,
  docName: (doc: { doc_id: string; name: Record<string, string> }) => string,
): NewVersionSummary => {
  const known = preview.docs.some((doc) => doc.change !== undefined);
  const changedIds = new Set(routeChangedDocs(route));
  const isChanged = (doc: SigningRoutePreview["docs"][number]): boolean =>
    known ? doc.change !== "same" : changedIds.has(doc.doc_id);
  const people = new Map(route.steps.flat().map((p) => [p.id, p]));
  return {
    changed: preview.docs.filter(isChanged).map(docName),
    kept: preview.docs.filter((doc) => !isChanged(doc)).map(docName),
    reapprove: preview.participants.flatMap((p) => {
      const person = people.get(p.participant_id);
      if (p.keeps_approval !== false || !person) return [];
      if (person.approved_at === null || person.user_id === meId) return [];
      return [person];
    }),
  };
};
