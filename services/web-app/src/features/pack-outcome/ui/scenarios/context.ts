import { createContext, useContext } from "react";
import type {
  PackScenarioEntry,
  PackScenarioRun,
  PackScenarioRunResult,
} from "@entities/pack-studio";
import type { RunTally } from "../../lib/scenarios";

/** Какое окно сценариев открыто: список выбора, новое из вводных, панель выбранного, копия, запись вводных. */
export type ScenarioDialog =
  | { kind: "picker" }
  | { kind: "create" }
  | { kind: "panel"; id: string }
  | { kind: "duplicate"; id: string }
  | { kind: "saveInputs"; id: string };

/**
 * Сценарии экрана «Результат»: список, прогон и действия над ними. Живёт в контексте, чтобы
 * верхняя панель, панель вводных и окна брали одно и то же и не ходили на сервер каждый сам.
 */
export type ScenarioUi = {
  entries: readonly PackScenarioEntry[];
  /** Список сценариев ещё загружается. */
  loading: boolean;
  /** Список не загрузился (повтор по `reload`). */
  loadFailed: unknown;
  reload: () => void;
  run: PackScenarioRun | undefined;
  /** Прогон идёт или не удался; пока результата нет, значки показывают «прогоняю» или «не прогнан». */
  runState: "loading" | "failed" | "ready";
  runError: unknown;
  /** Идёт ли прогон прямо сейчас (в том числе повторный при готовых результатах). */
  running: boolean;
  results: ReadonlyMap<string, PackScenarioRunResult>;
  tally: RunTally;
  /** Прогнать все сценарии заново. */
  rerun: () => void;
  /** Сценарии можно писать: рабочее дерево и режим автора. */
  canWrite: boolean;
  /** Причина запрета записи для подсказки; `null`, когда писать можно. */
  readOnlyReason: "student" | "state" | null;
  dialog: ScenarioDialog | null;
  open: (dialog: ScenarioDialog | null) => void;
  /** Удалить сценарий с «Отменить» на десять секунд; `true`, если удалён. */
  remove: (entry: PackScenarioEntry) => Promise<boolean>;
  /** Записать снимок текущего результата сценария; `true`, если записано. */
  accept: (entry: PackScenarioEntry) => Promise<boolean>;
};

export const ScenarioUiContext = createContext<ScenarioUi | null>(null);

/** Сценарии экрана; вне экрана «Результат» их нет. */
export const useScenarioUi = (): ScenarioUi | null =>
  useContext(ScenarioUiContext);
