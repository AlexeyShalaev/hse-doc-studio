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
      // «Локальная версия» облачной Студии на том же стенде server-lite.
      name: "local-studio",
      testMatch: /local-studio\.spec\.ts/,
      use: {
        ...devices["Desktop Chrome"],
        channel: process.env.E2E_CHANNEL || undefined,
      },
    },
    {
      // Лендинг на корне server-lite: гость, вход, телефон, ссылки как раньше, Open Graph, выключение админом.
      name: "landing",
      testMatch: /landing\.spec\.ts/,
      use: {
        ...devices["Desktop Chrome"],
        channel: process.env.E2E_CHANNEL || undefined,
      },
    },
    {
      // Подключённые Студии: локальная Студия и сервер с короткими интервалами присутствия (devices.spec.ts).
      name: "devices",
      testMatch: /devices\.spec\.ts/,
      timeout: 5 * 60_000,
      use: {
        ...devices["Desktop Chrome"],
        channel: process.env.E2E_CHANNEL || undefined,
      },
    },
    {
      // Телефон на server-lite: вход, список проектов, шторки, отсутствие горизонтальной прокрутки, зоны касания.
      // Размеры и касание задаёт сам сценарий (360x740, 390x844, планшет 820x1180).
      name: "mobile",
      testMatch: /(mobile(-admin|-rare)?|text-scale|stale-build)\.spec\.ts/,
      use: {
        ...devices["Pixel 7"],
        channel: process.env.E2E_CHANNEL || undefined,
      },
    },
    {
      // Passkey на server-lite: виртуальный аутентификатор Chrome через CDP (WebAuthn.addVirtualAuthenticator).
      name: "passkeys",
      testMatch: /passkeys\.spec\.ts/,
      use: {
        ...devices["Desktop Chrome"],
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
    {
      // Упавшая сборка объясняет себя: причина и журнал в облаке (личный раннер) и в локальной Студии.
      name: "build-failure",
      testMatch: /build-failure\.spec\.ts/,
      timeout: 20 * 60_000,
      use: {
        ...devices["Desktop Chrome"],
        actionTimeout: 30_000,
        channel: process.env.E2E_CHANNEL || undefined,
      },
    },
    {
      // Личный раннер вне сети compose и адрес S3 в ссылках (stack.sh outside-up, outside-mode); самостоятельный прогон.
      name: "outside-runner",
      testMatch: /outside-runner\.spec\.ts/,
      timeout: 30 * 60_000,
      use: {
        ...devices["Desktop Chrome"],
        channel: process.env.E2E_CHANNEL || undefined,
      },
    },
    {
      // Сервер как git-remote: токен «Для git», clone/push настоящим git, вход устройства по коду.
      name: "git-remote",
      testMatch: /git-remote\.spec\.ts/,
      timeout: 5 * 60_000,
      use: {
        ...devices["Desktop Chrome"],
        channel: process.env.E2E_CHANNEL || undefined,
      },
    },
    {
      // Бэкапы сервера: назначение, запуск, verify, восстановление; идёт на стенде deploy/server после полного смоука.
      name: "backups",
      testMatch: /backups\.spec\.ts/,
      timeout: 15 * 60_000,
      use: {
        ...devices["Desktop Chrome"],
        actionTimeout: 30_000,
        channel: process.env.E2E_CHANNEL || undefined,
      },
    },
    {
      // Доделка видения: ссылка-доступ, приглашения и запросы доступа, передача, git-remote для локальной Студии.
      name: "collab-finish",
      testMatch: /collab-finish\.spec\.ts/,
      timeout: 10 * 60_000,
      use: {
        ...devices["Desktop Chrome"],
        actionTimeout: 30_000,
        channel: process.env.E2E_CHANNEL || undefined,
      },
    },
    {
      // Онбординг: анкета, экскурсия, демо-проект в песочнице, пропуск; идёт после полного смоука на том же стенде.
      name: "onboarding",
      testMatch: /onboarding\.spec\.ts/,
      timeout: 5 * 60_000,
      use: {
        ...devices["Desktop Chrome"],
        actionTimeout: 20_000,
        channel: process.env.E2E_CHANNEL || undefined,
      },
    },
    {
      // Люди в проекте: аватары, место, переход к документу, подпись у курсора, уход по окну присутствия;
      // идёт после полного смоука на том же стенде (compose.smoke.yml задаёт короткое окно).
      name: "presence",
      testMatch: /presence\.spec\.ts/,
      timeout: 5 * 60_000,
      use: {
        ...devices["Desktop Chrome"],
        actionTimeout: 20_000,
        channel: process.env.E2E_CHANNEL || undefined,
      },
    },
    {
      // Страница «Обновления» и закрытый протокол апдейтера; идёт после полного смоука на том же стенде.
      name: "updates",
      testMatch: /updates\.spec\.ts/,
      timeout: 3 * 60_000,
      use: {
        ...devices["Desktop Chrome"],
        actionTimeout: 15_000,
        channel: process.env.E2E_CHANNEL || undefined,
      },
    },
  ],
});
