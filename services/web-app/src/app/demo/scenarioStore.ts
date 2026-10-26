import { create } from "zustand";
import { persist } from "zustand/middleware";
import { DEFAULT_SCENARIO_ID, type DemoScenarioId } from "./scenarios";

type DemoScenarioState = {
  scenarioId: DemoScenarioId;
  setScenarioId: (id: DemoScenarioId) => void;
};

// Выбранный сценарий переживает перезагрузку страницы: так удобно разглядывать
// одно состояние, не выбирая его заново после каждого обновления.
export const useDemoScenarioStore = create<DemoScenarioState>()(
  persist(
    (set) => ({
      scenarioId: DEFAULT_SCENARIO_ID,
      setScenarioId: (scenarioId) => {
        set({ scenarioId });
      },
    }),
    { name: "hse-studio.gitDemoScenario" },
  ),
);
