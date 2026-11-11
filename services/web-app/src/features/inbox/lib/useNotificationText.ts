import { useState } from "react";
import { useTranslation } from "react-i18next";
import { formatBytes } from "@shared/lib";
import { useProjectRoleLabel } from "@entities/project";
import type { Notification } from "@entities/invitation";
import { isSigningKind, showsDeadline } from "./notificationTarget";
import { formatDeadline } from "./signingTasks";

/**
 * Ключ текста: запрос раунда новой версии (signing-route.md, 12.6, `payload.new_version`) говорит
 * «просит подписать новую версию»; очистка диска раннера, которой нечего было освободить,
 * говорит «освобождать было нечего» (storage-cleanup.md, 8.2); остальные по виду уведомления.
 */
const textKind = (n: Notification): string => {
  if (n.kind === "signing_request" && n.payload.new_version) {
    return "signing_request_new_version";
  }
  if (
    n.kind === "runner_disk_cleaned" &&
    n.payload.outcome === "done" &&
    n.payload.freed_bytes === 0
  ) {
    return "runner_disk_cleaned_nothing";
  }
  return n.kind;
};

/** Освобождено очисткой диска раннера, как в окне «Диск»: ноль пишется числом. */
const freedSize = (n: Notification): string => {
  if (n.kind !== "runner_disk_cleaned") return "";
  const bytes = n.payload.freed_bytes ?? 0;
  return bytes > 0 ? formatBytes(bytes) : "0 MB";
};

/** Текст уведомления на языке интерфейса: общий для страницы «Входящие» и окошка колокольчика. */
export const useNotificationText = () => {
  const { t } = useTranslation("inbox");
  const roleLabel = useProjectRoleLabel();
  return (n: Notification): string =>
    t(`kind.${textKind(n)}`, {
      actor:
        n.payload.actor_name ??
        (isSigningKind(n.kind) ? t("signing.someone") : ""),
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
      // Очистка диска раннера: `excerpt` это имя раннера.
      name: n.payload.excerpt ?? "",
      size: freedSize(n),
      ...(n.payload.outcome ? { context: n.payload.outcome } : {}),
    });
};

/**
 * Подробности уведомления маршрута подписания рядом с текстом: проект и, у запроса и
 * напоминания, срок. Текст называет только точку, как письмо (раздел 3.2). У очистки диска
 * раннера администратор, который её запустил. У прочих null.
 */
export const useNotificationDetails = () => {
  const { t } = useTranslation("inbox");
  const [now] = useState(() => Date.now());
  return (n: Notification): string | null => {
    // Очистка диска раннера: кто из администраторов её запустил.
    if (n.kind === "runner_disk_cleaned") {
      return n.payload.actor_name
        ? t("runnerDisk.actor", { name: n.payload.actor_name })
        : null;
    }
    if (!isSigningKind(n.kind)) return null;
    const parts: string[] = [];
    if (n.payload.project_name) parts.push(n.payload.project_name);
    if (showsDeadline(n.kind) && n.payload.deadline) {
      parts.push(
        t("signing.deadline", {
          date: formatDeadline(n.payload.deadline, now),
        }),
      );
    }
    return parts.length > 0 ? parts.join(" · ") : null;
  };
};
