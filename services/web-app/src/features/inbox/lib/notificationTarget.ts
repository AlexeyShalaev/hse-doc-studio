import { signingCardPath, signingPagePath } from "@entities/signing-route";
import type { Notification } from "@entities/invitation";
import { myRunnerDiskPath } from "@entities/runner";

/**
 * Куда ведёт уведомление: ревью открывает файл и тред в панели комментариев (тред к месту
 * в PDF открывается в превью документа), остальное проект.
 */
export const notificationTarget = (n: Notification): string => {
  const project = `/projects/${n.payload.project_id ?? ""}`;
  if (n.kind.startsWith("review_") && n.payload.doc_id) {
    const params = new URLSearchParams();
    if (n.payload.ref_id) params.set("thread", n.payload.ref_id);
    const query = params.toString();
    return `${project}/documents/${encodeURIComponent(n.payload.doc_id)}${query ? `?${query}` : ""}`;
  }
  if (n.kind.startsWith("review_") && n.payload.path) {
    const params = new URLSearchParams({ file: n.payload.path });
    if (n.payload.ref_id) params.set("thread", n.payload.ref_id);
    return `${project}/files?${params.toString()}`;
  }
  return project;
};

/** Раздел «На подпись» на странице «Входящие». */
export const SIGNING_INBOX_PATH = "/inbox?tab=signing";

/**
 * Уведомления маршрута подписания для подписанта: зовут действовать или предупреждают о новой
 * версии (запрос придёт в его очередь, страница подписи пока пишет «Пока не ваша очередь»).
 */
const SIGNER_KINDS: ReadonlySet<Notification["kind"]> = new Set([
  "signing_request",
  "signing_reminder",
  "signing_new_version",
]);

export const isSigningKind = (kind: Notification["kind"]): boolean =>
  kind.startsWith("signing_");

/** Запрос и напоминание несут срок, его стоит показать рядом с текстом. */
export const showsDeadline = (kind: Notification["kind"]): boolean =>
  SIGNER_KINDS.has(kind);

/**
 * Маршрут подписания (6.6): запрос, напоминание и новая версия (12.6) ведут подписанта на его
 * страницу; возврат, остановка (в том числе `sent_changed`, когда автору нужно отправить новую
 * версию), завершение и отмена ведут к карточке «Подписание» на точке сдачи, где автор видит ход
 * маршрута и отправляет заново. `ref_id` это id маршрута, `profile_id` точка.
 */
const signingTarget = (n: Notification): string | null => {
  const { project_id: project, ref_id: route, profile_id: profile } = n.payload;
  if (!project) return null;
  if (SIGNER_KINDS.has(n.kind) && route) return signingPagePath(project, route);
  if (profile) return signingCardPath(project, profile);
  return `/projects/${encodeURIComponent(project)}`;
};

/** Маршрут по клику на уведомление; null, если идти некуда (например, «вас убрали из проекта»). */
export const notificationRoute = (n: Notification): string | null => {
  if (n.kind === "backup_failed") return "/admin/backups";
  // Очистка диска личного раннера администратором (storage-cleanup.md, 8.2): `ref_id` это id
  // раннера, переход открывает его «Диск» в «Моих раннерах».
  if (n.kind === "runner_disk_cleaned") {
    return myRunnerDiskPath(n.payload.ref_id);
  }
  if (n.kind === "system_alert") {
    return n.payload.outcome?.startsWith("update_")
      ? "/admin/updates"
      : n.payload.outcome?.startsWith("diag_")
        ? "/admin/diagnostics"
        : "/admin/data";
  }
  if (isSigningKind(n.kind)) return signingTarget(n);
  if (n.payload.project_id && n.kind !== "member_removed") {
    return notificationTarget(n);
  }
  return null;
};

/** Уведомления, на которые отвечают на странице «Входящие»: приглашение, передача, запрос доступа. */
const DECISION_KINDS: ReadonlySet<Notification["kind"]> = new Set([
  "project_invitation",
  "transfer_request",
  "access_request",
]);

export const needsDecision = (n: Notification): boolean =>
  n.read_at === null && DECISION_KINDS.has(n.kind);

/**
 * Клик в окошке колокольчика. Непрочитанное приглашение, передачу и запрос доступа решают
 * кнопками на странице «Входящие», поэтому ведём туда; запрос доступа остаётся непрочитанным
 * до решения: карточка с кнопками живёт на странице, пока он такой.
 */
export const popoverAction = (
  n: Notification,
): { route: string | null; markRead: boolean } => {
  if (needsDecision(n)) {
    return { route: "/inbox", markRead: n.kind !== "access_request" };
  }
  return { route: notificationRoute(n), markRead: n.read_at === null };
};
