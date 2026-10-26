import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { SyncUi } from "./syncUi.model";

export type SyncAnnouncement = { polite: string; assertive: string };

const EMPTY: SyncAnnouncement = { polite: "", assertive: "" };

type Seen = {
  state: SyncUi["state"];
  incoming: number;
};

/**
 * Что сказать скринридеру: только переходы между состояниями, а не каждый опрос.
 * Спокойные события (синхронизация закончилась, пришли новые версии) идут
 * вежливо, остановки (конфликты, отказ доступа, сбой) настойчиво.
 * Первое состояние при открытии проекта не объявляется.
 */
export const useSyncAnnouncer = (ui: SyncUi): SyncAnnouncement => {
  const { t } = useTranslation("gitSync");
  const [seen, setSeen] = useState<Seen | null>(null);
  const [announcement, setAnnouncement] = useState<SyncAnnouncement>(EMPTY);

  if (ui.visible) {
    const next: Seen = {
      state: ui.state,
      incoming: ui.incoming,
    };
    const unchanged =
      seen !== null &&
      seen.state === next.state &&
      seen.incoming === next.incoming;
    if (!unchanged) {
      // Состояние подстраиваем прямо в рендере: эффект дал бы лишнюю перерисовку.
      setSeen(next);
      if (seen !== null) {
        const message = ((): SyncAnnouncement | null => {
          switch (ui.state) {
            case "up_to_date":
              return seen.state === "syncing"
                ? { polite: t("live.syncDone"), assertive: "" }
                : null;
            case "behind":
            case "diverged":
              return ui.incoming > seen.incoming
                ? {
                    polite: t("live.incoming", { count: ui.incoming }),
                    assertive: "",
                  }
                : null;
            case "conflicts":
              return {
                polite: "",
                assertive: t("live.conflicts", { count: ui.conflictFiles }),
              };
            case "auth_failed":
              return { polite: "", assertive: t("live.authFailed") };
            case "error":
              return { polite: "", assertive: t("live.syncFailed") };
            case "offline":
              return { polite: t("live.offline"), assertive: "" };
            default:
              return null;
          }
        })();
        if (message) setAnnouncement(message);
      }
    }
  }
  return announcement;
};
