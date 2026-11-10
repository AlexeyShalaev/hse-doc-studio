import {
  isActionable,
  type RouteEvent,
  type SigningStopReason,
  type SigningTask,
  type SigningTaskAction,
  type SigningTaskDoc,
  type SigningTaskMe,
  type SigningTaskPerson,
  type SigningTaskSlot,
} from "@entities/signing-route";
import type { PdfStamp } from "@shared/ui";

// Чистые правила страницы подписанта (docs/design/signing-route.md, раздел 3.2): что
// показать по задаче сервера. Всё, что решает экран, считается здесь и проверяется тестами.

export type SigningPerson = Pick<SigningTaskPerson, "name" | "persona">;

/** Что сейчас с подписантом и маршрутом: заголовок и текст страницы. */
export type SigningStatus =
  /** Его очередь; `resent`: документ изменился после его прошлого согласия. */
  | { kind: "turn"; action: SigningTaskAction; resent: boolean }
  /** Очередь ещё не дошла; `now`: кто действует сейчас. */
  | { kind: "not_yet"; now: SigningPerson[] }
  /** Согласовал до фиксации, ждёт итоговый PDF (раздел 4.2). */
  | { kind: "approved" }
  /** Своё сделал, маршрут идёт дальше; `next`: кто действует сейчас. */
  | { kind: "done"; next: SigningPerson[] }
  | { kind: "completed" }
  | {
      kind: "returned";
      byMe: boolean;
      who: string | null;
      comment: string | null;
    }
  | { kind: "paused"; reason: SigningStopReason | null }
  | { kind: "cancelled" }
  | { kind: "closed" }
  | { kind: "draft" };

const ACTING = new Set<SigningTaskPerson["state"]>([
  "to_approve",
  "to_approve_sign",
  "to_sign",
]);

const mePerson = (task: SigningTask): SigningTaskPerson | undefined =>
  task.steps.flat().find((person) => person.me);

/** Кто действует сейчас (кроме меня): чья очередь, и ещё не принявшие приглашение на текущем шаге. */
export const actingNow = (task: SigningTask): SigningPerson[] =>
  task.steps.flatMap((step, index) =>
    step
      .filter(
        (person) =>
          !person.me &&
          (ACTING.has(person.state) ||
            (person.state === "invited" &&
              index + 1 === task.route.current_step)),
      )
      .map(({ name, persona }) => ({ name, persona })),
  );

/** Последний возврат на доработку в текущем раунде: кто и с каким комментарием. */
export const lastReturn = (task: SigningTask): RouteEvent | null =>
  task.events
    .filter((e) => e.kind === "returned" && e.round === task.route.round)
    .at(-1) ?? null;

/**
 * Документ изменился после того, как подписант уже согласовал или подписал его в прошлом раунде
 * (раздел 3.2, «После сброса»): маршрут отправлен заново, и его снова просят.
 */
const isResent = (task: SigningTask): boolean => {
  if (task.route.round <= 1) return false;
  // Раунд новой версии объясняет плашка «Новая версия» (раздел 12.2), строка не повторяет её.
  if (task.route.new_version === true) return false;
  return task.events.some(
    (e) =>
      e.round < task.route.round &&
      (e.kind === "approved" || e.kind === "signed") &&
      e.participant_id === task.me.participant_id,
  );
};

export const signingStatus = (task: SigningTask): SigningStatus => {
  const { route, me } = task;
  switch (route.status) {
    case "completed":
      return { kind: "completed" };
    case "archived":
      return { kind: "closed" };
    case "cancelled":
      return { kind: "cancelled" };
    case "draft":
      return { kind: "draft" };
    case "paused":
      return { kind: "paused", reason: route.stop_reason };
    case "returned": {
      const event = lastReturn(task);
      return {
        kind: "returned",
        byMe: me.state === "returned",
        who: event?.who ?? null,
        comment: event?.comment ?? null,
      };
    }
    case "active":
      break;
  }
  if (isActionable(me.next_action)) {
    return { kind: "turn", action: me.next_action, resent: isResent(task) };
  }
  if (me.state === "done") return { kind: "done", next: actingNow(task) };
  // `waiting` с временем действия: согласовал до фиксации и ждёт её (раздел 5.3).
  if (me.state === "waiting" && mePerson(task)?.at) return { kind: "approved" };
  return { kind: "not_yet", now: actingNow(task) };
};

/**
 * Почему «Согласовать» пока нельзя: сервер ответит 409 `image_required` или `plate_required`.
 * Картинку и ключ задаёт блок «Как подписать» (срез W5).
 */
export type ApproveBlocker = "image" | "plate";

export const approveBlocker = (me: SigningTaskMe): ApproveBlocker | null => {
  if (me.method === "image" && !me.image_ready) return "image";
  if ((me.method === "detached" || me.method === "pades") && me.plate === null)
    return "plate";
  return null;
};

export { expectedTokens } from "@entities/signing-route";

/**
 * Документы, по которым действует главная кнопка: с отпечатком для `expected`. У документа без
 * изменений в раунде новой версии отпечатка нет, согласие и подпись по нему остались (12.9).
 */
export const actionDocs = (task: SigningTask): SigningTaskDoc[] =>
  task.docs.filter((doc) => doc.token !== null);

/** Документы, изменившиеся в новой версии: `changed_since_mine` или `changed_docs` события `sent` раунда. */
const changedInRound = (task: SigningTask): Set<string> => {
  const sent = task.events
    .filter((e) => e.kind === "sent" && e.round === task.route.round)
    .at(-1);
  return new Set([
    ...(sent?.changed_docs ?? []),
    ...task.docs
      .filter((doc) => doc.changed_since_mine === true)
      .map((doc) => doc.doc_id),
  ]);
};

/**
 * «Новая версия: изменился документ …» (раздел 12.2): раунд новой версии, в котором изменился
 * хотя бы один документ участника; null в обычном раунде.
 */
export const newVersionDocs = (task: SigningTask): SigningTaskDoc[] | null => {
  if (task.route.new_version !== true) return null;
  const changed = changedInRound(task);
  const docs = task.docs.filter((doc) => changed.has(doc.doc_id));
  return docs.length > 0 ? docs : null;
};

export type KeptMark = "approved" | "signed";

/**
 * Пометка «Без изменений» у документа раунда новой версии: он не менялся, согласие и подпись
 * участника по нему остались, делать ничего не нужно. В свою очередь это документ без отпечатка;
 * до и после неё участник уже действовал (время действия есть).
 */
export const keptMark = (
  task: SigningTask,
  doc: SigningTaskDoc,
): KeptMark | null => {
  if (task.route.new_version !== true) return null;
  if (changedInRound(task).has(doc.doc_id)) return null;
  const kept = isActionable(task.me.next_action)
    ? doc.token === null
    : Boolean(mePerson(task)?.at);
  if (!kept) return null;
  return doc.mine.length > 0 && doc.mine.every((s) => s.status === "signed")
    ? "signed"
    : "approved";
};

export type VersionLineKind =
  "signing" | "signedMine" | "approvedMine" | "kept" | "signed";

/**
 * Строка версии над документом: «Вы подписываете версию от …»; своё сделано: «Вы подписали
 * (согласовали) версию от …»; документ без изменений в новой версии: «Версия на подписи от …»;
 * маршрут завершён: «Подписана версия от …». null, пока версии на подписи нет (до R16,
 * черновик, отмена).
 */
export const versionLine = (
  task: SigningTask,
  doc: SigningTaskDoc,
): { kind: VersionLineKind; at: string } | null => {
  if (!doc.sent_at) return null;
  const kind = ((): VersionLineKind => {
    if (task.route.status === "completed" || task.route.status === "archived")
      return "signed";
    // Документ без изменений в новой версии: рядом пометка «Без изменений: вы уже …».
    if (keptMark(task, doc)) return "kept";
    if (task.me.state !== "done") return "signing";
    return doc.mine.length > 0 ? "signedMine" : "approvedMine";
  })();
  return { kind, at: doc.sent_at };
};

/**
 * Плашка расхождения у автора и управляющего (12.2, п. 3 и 5): рабочая сборка документов ушла
 * от версии на подписи. `changed` у остальных null, поэтому плашку видят только они.
 * `sentAt`: дата версии на подписи первого изменившегося документа.
 */
export type Divergence = {
  docs: SigningTaskDoc[];
  completed: boolean;
  sentAt: string | null;
};

export const divergenceOf = (task: SigningTask): Divergence | null => {
  if (task.route.status === "archived") return null;
  const docs = task.docs.filter((doc) => doc.changed === true);
  if (docs.length === 0) return null;
  return {
    docs,
    completed: task.route.status === "completed",
    sentAt: docs.find((doc) => doc.sent_at)?.sent_at ?? null,
  };
};

/** Свои слоты документа, которые ещё ждут подписи. */
export const pendingMine = (doc: SigningTaskDoc): SigningTaskSlot[] =>
  doc.mine.filter((slot) => slot.status !== "signed");

// Высоту метки отдаёт сервер (`height_mm`). У слота без видимой метки её нет: рамка места
// берёт типичную пропорцию картинки.
const FRAME_ASPECT: Record<SigningTaskSlot["mark"], number> = {
  png: 0.4,
  plate: 0.55,
  none: 0.4,
};

export const frameHeightMm = (slot: SigningTaskSlot): number =>
  slot.height_mm ?? slot.width_mm * FRAME_ASPECT[slot.mark];

/** Рамки своих слотов поверх страниц PDF. */
export const myFrames = (doc: SigningTaskDoc, label: string): PdfStamp[] =>
  doc.mine.map((slot) => ({
    page: slot.page,
    src: null,
    xMm: slot.x_mm,
    yMm: slot.y_mm,
    widthMm: slot.width_mm,
    heightMm: frameHeightMm(slot),
    label,
    highlight: true,
  }));

const PT_PER_MM = 72 / 25.4;

export type PdfJumpTarget = {
  page: number;
  xPt: number;
  yPt: number;
  widthPt: number;
  heightPt: number;
  token: number;
};

/** Прокрутка PDF к слоту с подсветкой; `token` новый на каждое нажатие. */
export const jumpToSlot = (
  slot: SigningTaskSlot,
  token: number,
): PdfJumpTarget => ({
  page: slot.page,
  xPt: slot.x_mm * PT_PER_MM,
  yPt: slot.y_mm * PT_PER_MM,
  widthPt: slot.width_mm * PT_PER_MM,
  heightPt: frameHeightMm(slot) * PT_PER_MM,
  token,
});

/** Срок прошёл, а маршрут ещё идёт. */
export const isOverdue = (task: SigningTask, now: number): boolean =>
  task.route.status === "active" &&
  task.route.deadline !== null &&
  Date.parse(task.route.deadline) < now;
