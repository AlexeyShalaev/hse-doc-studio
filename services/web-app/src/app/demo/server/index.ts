import { useServerDemoScenarioStore } from "./scenarioStore";
import { findServerScenario } from "./scenarios";
import {
  resetServerWorld,
  serverDemoRoutes,
  setServerDemoActive,
} from "./routes";

export { serverDemoRoutes };
export { SERVER_SCENARIOS } from "./scenarios";
export { ServerDemoPicker } from "./ServerDemoPicker";

/** Включает серверный мир: маршруты уже в общем адаптере, здесь они оживают. */
export const enableServerDemo = (): void => {
  setServerDemoActive(true);
};

// Галерея /dev/server-screens ставит мир в нужный сценарий сама.
export const activateServerScenario = (scenarioId: string): void => {
  const scenario = findServerScenario(scenarioId);
  if (!scenario) return;
  resetServerWorld(scenario.id);
  useServerDemoScenarioStore.getState().setScenarioId(scenario.id);
};
