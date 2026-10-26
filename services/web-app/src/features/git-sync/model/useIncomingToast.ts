import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "@shared/lib";
import type { SyncView } from "./useSyncView";

// Уже показанные уведомления: по проекту и «голове» репозитория, на сессию
// вкладки. Без этого каждая перезагрузка страницы повторяла бы то же сообщение.
const SHOWN_KEY = "hse-studio.git-sync.incoming-notified";
const MAX_REMEMBERED = 100;

const readShown = (): string[] => {
  try {
    return (sessionStorage.getItem(SHOWN_KEY) ?? "")
      .split("\n")
      .filter(Boolean);
  } catch {
    return [];
  }
};

const wasShown = (key: string): boolean => readShown().includes(key);

const markShown = (key: string): void => {
  try {
    const next = [...readShown(), key].slice(-MAX_REMEMBERED);
    sessionStorage.setItem(SHOWN_KEY, next.join("\n"));
  } catch {
    // Хранилище недоступно: уведомление просто может повториться.
  }
};

/**
 * «Коллеги внесли изменения»: один раз за сессию на каждую новую «голову»
 * репозитория. Молчит, пока идёт синхронизация и когда у пользователя и так
 * открыты конфликты.
 */
export const useIncomingToast = (
  projectId: string,
  view: Pick<SyncView, "status" | "ui">,
  onSync: () => void,
): void => {
  const { t } = useTranslation("gitSync");
  const { status, ui } = view;
  const head = status?.incoming[0] ?? null;
  const isIncoming = ui.state === "behind" || ui.state === "diverged";
  const headId = head?.id ?? null;
  const author = head?.author ?? "";
  const count = ui.incoming;

  useEffect(() => {
    if (!isIncoming || headId === null) return;
    const key = `${projectId}:${headId}`;
    if (wasShown(key)) return;
    markShown(key);
    toast.info(t("toast.incomingMessage", { count, author }), {
      title: t("toast.incomingTitle"),
      duration: 10_000,
      action: { label: t("toast.sync"), onClick: onSync },
    });
    // onSync и t меняются от рендера к рендеру; уведомление зависит от данных.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, headId, isIncoming]);
};
