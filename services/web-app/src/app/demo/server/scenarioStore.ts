import { create } from "zustand";
import { persist } from "zustand/middleware";
import {
  DEFAULT_SERVER_SCENARIO_ID,
  type ServerDemoScenarioId,
} from "./scenarios";

type ServerDemoScenarioState = {
  scenarioId: ServerDemoScenarioId;
  setScenarioId: (id: ServerDemoScenarioId) => void;
};

// Выбранный сценарий переживает перезагрузку: удобно разглядывать одно состояние.
export const useServerDemoScenarioStore = create<ServerDemoScenarioState>()(
  persist(
    (set) => ({
      scenarioId: DEFAULT_SERVER_SCENARIO_ID,
      setScenarioId: (scenarioId) => {
        set({ scenarioId });
      },
    }),
    { name: "hse-studio.serverDemoScenario" },
  ),
);
