import { apiClient } from "@shared/api";
import { createDemoRouter, installDemoAdapter } from "@shared/api/demo";
import { gitDemoRoutes } from "./routes";

// Демо-режим синхронизации (VITE_GIT_DEMO=1): ответы по git, профилю и доступам
// отдаёт память вкладки, остальные запросы идут настоящему бэкенду. Подключается
// из main.tsx динамическим импортом и в обычную сборку не попадает.
export const installGitDemo = (): void => {
  installDemoAdapter(apiClient, createDemoRouter(gitDemoRoutes), {
    latencyMs: 180,
    uploadStepMs: 300,
  });
};

export { DemoScenarioPicker } from "./DemoScenarioPicker";
