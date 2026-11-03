import type { Notification } from "@entities/invitation";

/** Куда ведёт уведомление: ревью открывает файл и тред в панели комментариев, остальное проект. */
export const notificationTarget = (n: Notification): string => {
  const project = `/projects/${n.payload.project_id ?? ""}`;
  if (n.kind.startsWith("review_") && n.payload.path) {
    const params = new URLSearchParams({ file: n.payload.path });
    if (n.payload.ref_id) params.set("thread", n.payload.ref_id);
    return `${project}/files?${params.toString()}`;
  }
  return project;
};

/** Маршрут по клику на уведомление; null, если идти некуда (например, «вас убрали из проекта»). */
export const notificationRoute = (n: Notification): string | null => {
  if (n.kind === "backup_failed") return "/admin/backups";
  if (n.kind === "system_alert") {
    return n.payload.outcome?.startsWith("update_")
      ? "/admin/updates"
      : n.payload.outcome?.startsWith("diag_")
        ? "/admin/diagnostics"
        : "/admin/data";
  }
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
