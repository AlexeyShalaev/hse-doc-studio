import { apiClient } from "@shared/api";
import { createDemoRouter, installDemoAdapter } from "@shared/api/demo";
import { gitDemoRoutes, resetWorld } from "./routes";
import { useDemoScenarioStore } from "./scenarioStore";
import { SCENARIOS } from "./scenarios";

// Демо-режим синхронизации (VITE_GIT_DEMO=1): ответы по git, профилю и доступам
// отдаёт память вкладки, остальные запросы идут настоящему бэкенду. Подключается
// из main.tsx динамическим импортом и в обычную сборку не попадает.
let installed = false;

export const installGitDemo = (): void => {
  // Повторная установка обернула бы демо-транспорт в самого себя.
  if (installed) return;
  installed = true;
  installDemoAdapter(apiClient, createDemoRouter(gitDemoRoutes), {
    latencyMs: 180,
    uploadStepMs: 300,
  });
};

export { DemoScenarioPicker } from "./DemoScenarioPicker";

// Галерея состояний (/dev/sync-states) ставит мир в нужный сценарий сама, без
// переключателя в углу экрана. Неизвестный сценарий игнорируется.
export const activateDemoScenario = (scenarioId: string): void => {
  const scenario = SCENARIOS.find((item) => item.id === scenarioId);
  if (!scenario) return;
  resetWorld(scenario.id);
  useDemoScenarioStore.getState().setScenarioId(scenario.id);
};
