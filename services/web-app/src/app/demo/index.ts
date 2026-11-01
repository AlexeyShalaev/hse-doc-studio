import { adminClient, apiClient } from "@shared/api";
import { systemClient } from "@entities/system";
import { createDemoRouter, installDemoAdapter } from "@shared/api/demo";
import { gitDemoRoutes, resetWorld } from "./routes";
import { useDemoScenarioStore } from "./scenarioStore";
import { SCENARIOS } from "./scenarios";
import {
  enableServerDemo,
  serverAdminDemoRoutes,
  serverDemoRoutes,
  serverSystemDemoRoutes,
} from "./server";

// Демо-режим синхронизации (VITE_GIT_DEMO=1): ответы по git, профилю и доступам
// отдаёт память вкладки, остальные запросы идут настоящему бэкенду. Подключается
// из main.tsx динамическим импортом и в обычную сборку не попадает.
let installed = false;

export const installGitDemo = (): void => {
  // Повторная установка обернула бы демо-транспорт в самого себя.
  if (installed) return;
  installed = true;
  installDemoAdapter(
    apiClient,
    createDemoRouter([...serverDemoRoutes, ...gitDemoRoutes]),
    {
      latencyMs: 180,
      uploadStepMs: 300,
    },
  );
  // Админка ходит другим клиентом (/api/admin): ему свой набор демо-маршрутов.
  installDemoAdapter(adminClient, createDemoRouter(serverAdminDemoRoutes), {
    latencyMs: 180,
  });
  // Сведения о сервере идут своим клиентом мимо общего перехватчика ошибок.
  installDemoAdapter(systemClient, createDemoRouter(serverSystemDemoRoutes));
};

// Серверное демо (VITE_SERVER_DEMO=1): сессия, вход и мастер первого запуска на
// данных вкладки. Транспорт общий с демо git, поэтому оба мира живут вместе.
export const installServerDemo = (): void => {
  installGitDemo();
  enableServerDemo();
};

export { ServerDemoPicker, activateServerScenario } from "./server";
export { DemoScenarioPicker } from "./DemoScenarioPicker";

// Галерея состояний (/dev/sync-states) ставит мир в нужный сценарий сама, без
// переключателя в углу экрана. Неизвестный сценарий игнорируется.
export const activateDemoScenario = (scenarioId: string): void => {
  const scenario = SCENARIOS.find((item) => item.id === scenarioId);
  if (!scenario) return;
  resetWorld(scenario.id);
  useDemoScenarioStore.getState().setScenarioId(scenario.id);
};
