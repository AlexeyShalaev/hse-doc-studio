import { useTranslation } from "react-i18next";
import { formatPastTime } from "@shared/lib";
import type { SyncUi } from "./syncUi.model";

export type SyncText = {
  /** Короткая подпись на кнопке. */
  label: string;
  /** Полная фраза состояния: для подсказки, имени кнопки и строки состояния. */
  status: string;
  /** Подсказка, что произойдёт по щелчку. */
  action: string;
  /** Название этапа идущей операции. */
  phase: string | null;
  /** «3 минуты назад»: когда проект последний раз синхронизировали. */
  when: string;
};

// Подписи состояния на языке интерфейса. Относительное время («3 мин назад»)
// считается от `now`: вызывающий обновляет его по таймеру.
export const useSyncText = (ui: SyncUi, now: number): SyncText => {
  const { t } = useTranslation("gitSync");

  const phase = ((): string | null => {
    if (ui.operationKind !== null) {
      return t(`operationKind.${ui.operationKind}`, {
        defaultValue: t("control.status.syncingPlain"),
      });
    }
    if (ui.phase === null) return null;
    return t(`phase.${ui.phase}`);
  })();

  const when = formatPastTime(ui.since, now);
  const params: Record<string, string | number> = {
    ...ui.statusParams,
    when,
    phase: phase ?? t("control.status.syncingPlain"),
    studio: ui.requiredStudio ?? "",
  };

  return {
    label:
      ui.state === "syncing"
        ? (phase ?? t("control.status.syncingPlain"))
        : t(ui.labelKey),
    status: t(ui.statusKey, params),
    action: t(`control.action.${ui.primary}`),
    phase,
    when,
  };
};
