import { demoJson } from "@shared/api/demo";
import type { DemoRoute } from "@shared/api/demo";
import type { ServerDemoWorld } from "./world";

// Сведения о сервере (/system/*) в демо. Клиент systemClient ходит мимо общего
// apiClient, поэтому эти маршруты ставятся на него отдельно. Без них каждый
// экран серверного демо ронял запросы на несуществующий бэкенд.

export const createSystemRoutes = (
  getWorld: () => ServerDemoWorld,
): DemoRoute[] => [
  {
    method: "GET",
    pattern: "/system/info",
    handler: () =>
      demoJson({
        version: getWorld().bootstrap.version,
        mode: "server",
        deployment_mode: "standard",
        os: "linux",
        os_version: "Ubuntu 24.04",
        python_version: "3.13.1",
        image_ref: `ghcr.io/hse-doc-studio/api:${getWorld().bootstrap.version}`,
        source_url: "https://github.com/hse-doc-studio/hse-doc-studio",
        github_repo: "hse-doc-studio/hse-doc-studio",
        license: "MIT",
        docker: "running",
        can_self_update: false,
        built: "2026-10-20T09:00:00Z",
        latest_version: getWorld().bootstrap.version,
        update_available: false,
        update_checked_at: null,
        update_feed_enabled: false,
        latest_release_date: "",
        latest_release_notes: [],
      }),
  },
  {
    method: "GET",
    pattern: "/system/runner-health",
    handler: () => demoJson({ docker: "running" }),
  },
];
