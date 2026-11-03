import { useTranslation } from "react-i18next";
import { useProjectRoleLabel } from "@entities/project";
import type { Notification } from "@entities/invitation";

/** Текст уведомления на языке интерфейса: общий для страницы «Входящие» и окошка колокольчика. */
export const useNotificationText = () => {
  const { t } = useTranslation("inbox");
  const roleLabel = useProjectRoleLabel();
  return (n: Notification): string =>
    t(`kind.${n.kind}`, {
      actor: n.payload.actor_name ?? "",
      project: n.payload.project_name ?? "",
      path: n.payload.path ?? "",
      excerpt: n.payload.excerpt ?? "",
      volume: n.payload.ref_id ?? "",
      check: n.payload.outcome?.startsWith("diag_")
        ? t(`diagCheck.${n.payload.ref_id ?? ""}`, {
            defaultValue: n.payload.ref_id ?? "",
          })
        : "",
      role: n.payload.role ? roleLabel(n.payload.role as "reader") : "",
      ...(n.payload.outcome ? { context: n.payload.outcome } : {}),
    });
};
