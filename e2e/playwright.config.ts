import { defineConfig, devices } from "@playwright/test";

// Стенд поднимает make e2e-stand-up (или шаг CI); адрес и учётные данные приходят из окружения.
const baseURL = process.env.E2E_BASE_URL ?? "http://localhost:8100";

export default defineConfig({
  testDir: "./tests",
  // Сценарии идут по одному воркеру: они делят одну базу стенда, а изоляция проверяется именно между пользователями.
  workers: 1,
  fullyParallel: false,
  retries: process.env.CI ? 1 : 0,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  reporter: process.env.CI
    ? [["list"], ["html", { open: "never" }]]
    : [["list"]],
  outputDir: "test-results",
  use: {
    baseURL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    viewport: { width: 1360, height: 860 },
  },
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        // Локально можно взять установленный Chrome: E2E_CHANNEL=chrome.
        channel: process.env.E2E_CHANNEL || undefined,
      },
    },
  ],
});
