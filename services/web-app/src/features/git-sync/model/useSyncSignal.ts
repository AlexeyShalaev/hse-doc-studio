import { useSyncView } from "./useSyncView";
import type { SyncUi } from "./syncUi.model";

export type SyncSignal = {
  /** Бейдж на кнопке «История»: конфликты > доступ и ошибки > новое в репозитории. */
  badge: SyncUi["railBadge"];
  /** Состояние, ради которого бейдж: от него зависит подсказка рейки. */
  state: SyncUi["state"] | null;
  /** Есть ли повод привлечь внимание. */
  hasSignal: boolean;
};

const NONE: SyncSignal = { badge: null, state: null, hasSignal: false };

/**
 * Единый источник «синхронизации есть что сказать» для рейки. Счётчик
 * несохранённых файлов остаётся прежним и показывается, когда сказать нечего:
 * его подставляет оболочка, у которой этот счётчик уже есть.
 */
export const useSyncSignal = (projectId: string): SyncSignal => {
  const { ui } = useSyncView(projectId);
  if (!ui.visible || ui.railBadge === null) return NONE;
  return { badge: ui.railBadge, state: ui.state, hasSignal: true };
};
