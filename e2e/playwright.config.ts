import { defineConfig, devices } from "@playwright/test";

// Стенд поднимает make server-lite-up server-lite-seed (или шаг CI); адрес и учётные данные приходят из окружения.
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
      // Приёмка M1 на лёгком стенде server-lite.
      name: "m1",
      testMatch: /m1\.spec\.ts/,
      use: {
        ...devices["Desktop Chrome"],
        // Локально можно взять установленный Chrome: E2E_CHANNEL=chrome.
        channel: process.env.E2E_CHANNEL || undefined,
      },
    },
    {
      // Полный смоук на стенде deploy/server (make server-stack-up, make e2e-full).
      name: "full",
      testMatch: /full\.spec\.ts/,
      timeout: 15 * 60_000,
      use: {
        ...devices["Desktop Chrome"],
        channel: process.env.E2E_CHANNEL || undefined,
      },
    },
    {
      // Личные раннеры на том же стенде с оверлеем compose.personal.yml; идёт после полного смоука.
      name: "personal",
      testMatch: /personal\.spec\.ts/,
      timeout: 20 * 60_000,
      use: {
        ...devices["Desktop Chrome"],
        channel: process.env.E2E_CHANNEL || undefined,
      },
    },
    {
      // Личные раннеры, самостоятельный прогон на своём стенде (stack.sh up, затем этот проект).
      name: "personal-runners",
      testMatch: /personal-runners\.spec\.ts/,
      timeout: 30 * 60_000,
      use: {
        ...devices["Desktop Chrome"],
        // Сценарий длинный (сборки TeX), но щелчок по пропавшему элементу не должен ждать до конца теста.
        actionTimeout: 30_000,
        channel: process.env.E2E_CHANNEL || undefined,
      },
    },
  ],
});
