import { env } from "@shared/config";
import type {
  ParticipantState,
  SigningNextAction,
  SigningRouteStatus,
  SigningTask,
  SigningTaskAction,
} from "../model/signingRoute.schema";

// Правила статусов маршрута из раздела 5 дизайна: какие действия доступны в каком статусе.

/** Незавершённый маршрут точки: такой может быть только один (уникальный индекс). */
export const isRouteOpen = (status: SigningRouteStatus): boolean =>
  status === "draft" ||
  status === "active" ||
  status === "paused" ||
  status === "returned";

/** PUT разрешён: шаги, люди, срок и сообщение меняются только вне активного маршрута. */
export const isRouteEditable = (status: SigningRouteStatus): boolean =>
  status === "draft" ||
  status === "paused" ||
  status === "returned" ||
  status === "cancelled";

/** «Отправить» из черновика или «Отправить заново» после остановки, возврата или отмены. */
export const canSendRoute = isRouteEditable;

/** Повторная отправка: маршрут уже уходил подписантам. */
export const isResend = (status: SigningRouteStatus): boolean =>
  status === "paused" || status === "returned" || status === "cancelled";

/**
 * Документы, рабочая сборка которых ушла от версии на подписи (раздел 12.9). Поля нет в ответах
 * сервера до среза R16: тогда изменений нет.
 */
export const routeChangedDocs = (route: {
  changed_docs?: readonly string[] | undefined;
}): readonly string[] => route.changed_docs ?? [];

export type RouteSendKind = "send" | "resend" | "new_version";

/**
 * Какую отправку предлагать (раздел 12.6): «Отправить» у черновика; «Отправить новую версию»,
 * когда у документов есть изменения (из идущего, остановленного, возвращённого и завершённого);
 * «Отправить заново» без изменений после остановки, возврата или отмены; null: отправлять нечего
 * (идущий и завершённый без изменений, снятый с контроля). Все три это `POST .../send`.
 */
export const routeSendKind = (
  status: SigningRouteStatus,
  changedDocs: readonly string[],
): RouteSendKind | null => {
  if (status === "draft") return "send";
  if (status === "archived") return null;
  if (changedDocs.length > 0) return "new_version";
  return isResend(status) ? "resend" : null;
};

export const canCancelRoute = (status: SigningRouteStatus): boolean =>
  status === "draft" ||
  status === "active" ||
  status === "paused" ||
  status === "returned";

export const canArchiveRoute = (status: SigningRouteStatus): boolean =>
  status === "completed";

/** Маршрут ещё меняется сам (чужие действия, фиксация): его стоит перечитывать. */
export const isRouteLive = (status: SigningRouteStatus): boolean =>
  status === "active";

/** Подписанту сейчас есть что сделать. */
export const isActionable = (
  action: SigningNextAction,
): action is SigningTaskAction =>
  action === "approve" || action === "approve_and_sign" || action === "sign";

/** «Вернуть на доработку» доступно участнику только в его очередь (раздел 5.6). */
export const canReturnForRework = (state: ParticipantState): boolean =>
  state === "to_approve" || state === "to_approve_sign" || state === "to_sign";

/** «Напомнить» имеет смысл тем, чья очередь, и приглашённым. */
export const canRemind = (state: ParticipantState): boolean =>
  canReturnForRework(state) || state === "invited";

/** Ручное напоминание не чаще раза в 12 часов на человека (раздел 5.7). */
export const REMIND_INTERVAL_MS = 12 * 60 * 60 * 1000;

export const nextRemindAt = (remindedAt: string | null): number | null =>
  remindedAt === null ? null : Date.parse(remindedAt) + REMIND_INTERVAL_MS;

/** Страница подписанта (раздел 3.2); адрес без токена, нужна авторизация. */
export const signingPagePath = (projectId: string, routeId: string): string =>
  `/sign/${encodeURIComponent(projectId)}/${encodeURIComponent(routeId)}`;

/** Страница контрольной точки: там карточка «Подписание» с ходом её маршрута. */
export const checkpointPath = (projectId: string, profileId: string): string =>
  `/projects/${encodeURIComponent(projectId)}/submit/cp/${encodeURIComponent(profileId)}`;

/** Экран автора «Отправка на подписание» для контрольной точки (раздел 3.1). */
export const signingRouteEditorPath = (
  projectId: string,
  profileId: string,
): string => `${checkpointPath(projectId, profileId)}/route`;

/** Адрес PDF документа задачи: `pdf_url` бэкенда уже начинается с `/api/v1`. */
export const signingPdfUrl = (pdfUrl: string): string =>
  `${env.VITE_API_BASE_URL}${pdfUrl}`;

/** Отпечатки последнего показа для `expected`: только документы, где сервер их дал. */
export const expectedTokens = (task: SigningTask): Record<string, string> =>
  Object.fromEntries(
    task.docs.flatMap((doc) =>
      doc.token === null ? [] : [[doc.doc_id, doc.token] as const],
    ),
  );
