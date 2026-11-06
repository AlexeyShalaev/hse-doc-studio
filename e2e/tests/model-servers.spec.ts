import { expect, test, type Page, type Route } from "@playwright/test";
import { LANGS, shot, type Lang } from "./helpers";
import { expectNoHorizontalScroll, loginOnPhone } from "./phoneHelpers";

/**
 * Админка, «Серверы моделей», на подменённом API (стенд server-lite без Docker): железо и подсказки, оценка до
 * скачивания, установка с ходом по шагам, запуск и остановка, журнал, удаление; на телефоне ничего не торчит за край.
 * Подмена держит состояние сервера, как это делает настоящий бэкенд.
 * Скриншоты: screenshots/<язык>/ms-*.png.
 */
const ADMIN_EMAIL = process.env.E2E_ADMIN_EMAIL ?? "admin@example.org";
const adminPassword = (): string => {
  const value = process.env.E2E_ADMIN_PASSWORD;
  if (!value) {
    throw new Error(
      "E2E_ADMIN_PASSWORD не задан: возьмите SERVER_LITE_ADMIN_PASSWORD из server-lite/.env",
    );
  }
  return value;
};

type Server = Record<string, unknown>;

const CAPS = {
  local_enabled: true,
  docker_available: true,
  hardware: {
    gpu_vendor: "none",
    gpu_name: null,
    vram_mb: null,
    total_ram_mb: 16384,
    cpu_count: 8,
    docker_gpu_supported: false,
    arch: "x86_64",
    disk_free_mb: 200000,
  },
  engines: [
    {
      engine: "ollama",
      image: "ollama/ollama:0.40.15",
      available: true,
      reasons: [],
    },
    {
      engine: "vllm",
      image: "vllm/vllm-openai:v0.32.0",
      available: false,
      reasons: ["engine_requires_gpu"],
    },
    {
      engine: "sglang",
      image: "lmsysorg/sglang:v0.5.23",
      available: false,
      reasons: ["engine_requires_gpu"],
    },
  ],
};

const STEPS_DONE = {
  container: "done",
  engine: "done",
  model: "done",
  provider: "done",
  verify: "done",
};

/** Подмена API: установка идёт два опроса, потом сервер работает. */
const mockApi = async (page: Page): Promise<{ calls: string[] }> => {
  const calls: string[] = [];
  let server: Server | null = null;
  let polls = 0;
  const json = (route: Route, body: unknown, status = 200) =>
    route.fulfill({
      status,
      contentType: "application/json",
      body: JSON.stringify(body),
    });

  await page.route("**/api/admin/model-servers**", async (route) => {
    const req = route.request();
    const path = new URL(req.url()).pathname.replace(
      "/api/admin/model-servers",
      "",
    );
    calls.push(`${req.method()} ${path || "/"}`);
    if (path === "/capabilities") return json(route, CAPS);
    if (path === "/catalog") {
      return json(route, {
        items: [
          { ref: "qwen3:4b", title: "Qwen3 4B", params_b: 4, quant: "q4" },
        ],
      });
    }
    if (path === "/estimate") {
      return json(route, {
        fit: "fits",
        params_b: 4,
        weights_mb: 2400,
        needed_mb: 3000,
        available_mb: 16384,
        memory_kind: "ram",
        disk_ok: true,
        reasons: [],
      });
    }
    if (path === "" && req.method() === "POST") {
      const body = req.postDataJSON() as { engine: string; model: string };
      polls = 0;
      server = {
        id: "e2e1",
        engine: body.engine,
        model: body.model,
        name: `${body.engine} ${body.model}`,
        status: "installing",
        endpoint: null,
        provider_id: null,
        image: "ollama/ollama:0.40.15",
        steps: {
          container: "done",
          engine: "done",
          model: "running",
          provider: "pending",
          verify: "pending",
        },
        percent: 40,
        text: "pulling",
        error: null,
      };
      return json(route, server, 202);
    }
    if (path === "" && req.method() === "GET") {
      if (server?.status === "installing" && ++polls > 2) {
        server = {
          ...server,
          status: "running",
          steps: STEPS_DONE,
          percent: 100,
          provider_id: "11111111-1111-1111-1111-111111111111",
          endpoint: "http://hse-ms-e2e1:11434",
        };
      }
      return json(route, { items: server ? [server] : [] });
    }
    if (path === "/e2e1/stop" && server) {
      server = { ...server, status: "stopped" };
      return json(route, server);
    }
    if (path === "/e2e1/start" && server) {
      server = { ...server, status: "running" };
      return json(route, server);
    }
    if (path === "/e2e1/logs")
      return json(route, { text: "ollama serve: listening on 11434" });
    if (path === "/e2e1" && req.method() === "DELETE") {
      server = null;
      return route.fulfill({ status: 204 });
    }
    return route.continue();
  });
  return { calls };
};

const login = async (page: Page): Promise<void> =>
  loginOnPhone(page, ADMIN_EMAIL, adminPassword());

for (const lang of LANGS) {
  const L = lang as Lang;
  const text = (ru: string, en: string): RegExp =>
    new RegExp(lang === "ru" ? ru : en, "i");

  test.describe(`Серверы моделей [${lang}]`, () => {
    test.use({ locale: lang === "ru" ? "ru-RU" : "en-US" });

    test("установка Ollama от подсказок до работающего сервера, запуск, остановка, журнал, удаление", async ({
      page,
    }) => {
      const api = await mockApi(page);
      await login(page);
      await page.goto("/admin/model-servers");

      await expect(page.getByTestId("ms-hardware")).toBeVisible();
      await expect(page.getByTestId("ms-engine-ollama")).toBeVisible();
      await expect(page.getByTestId("ms-engine-vllm")).toContainText(
        text("видеокарта NVIDIA", "NVIDIA GPU"),
      );
      await shot(page, L, "ms-10-hardware");

      await page.getByTestId("ms-model").fill("qwen3:4b");
      await expect(page.getByTestId("ms-estimate")).toContainText(
        text("Поместится", "Fits"),
      );
      await page.getByTestId("ms-install-submit").click();

      const card = page.getByTestId("ms-server-e2e1");
      await expect(card).toBeVisible();
      await shot(page, L, "ms-20-installing");
      await expect(card).toContainText(text("Работает", "Running"), {
        timeout: 20_000,
      });
      await expect(card).toContainText(
        text("общий ИИ-провайдер", "shared AI provider"),
      );

      await card
        .getByRole("button", { name: text("Остановить", "Stop") })
        .click();
      await expect(card).toContainText(text("Остановлен", "Stopped"));
      await card
        .getByRole("button", { name: text("Запустить", "Start") })
        .click();
      await expect(card).toContainText(text("Работает", "Running"));

      await page.getByTestId("ms-logs-e2e1").click();
      await expect(page.getByTestId("ms-logtext-e2e1")).toContainText(
        "listening on 11434",
      );
      await shot(page, L, "ms-30-running");

      await page.getByTestId("ms-remove-e2e1").click();
      const name = (await card.locator("strong").first().textContent()) ?? "";
      await page.getByRole("dialog").getByRole("textbox").fill(name);
      await page
        .getByRole("dialog")
        .getByRole("button", { name: text("Удалить", "Remove") })
        .click();
      await expect(card).toHaveCount(0);
      expect(api.calls).toContain("POST /");
      expect(api.calls).toContain("DELETE /e2e1");
    });

    test.describe("телефон 360", () => {
      test.use({
        viewport: { width: 360, height: 740 },
        hasTouch: true,
        isMobile: true,
      });

      test("страница без горизонтальной прокрутки", async ({ page }) => {
        await mockApi(page);
        await login(page);
        await page.goto("/admin/model-servers");
        await expect(page.getByTestId("ms-install")).toBeVisible();
        await page.getByTestId("ms-model").fill("qwen3:4b");
        await expect(page.getByTestId("ms-estimate")).toBeVisible();
        await expectNoHorizontalScroll(page);
        await shot(page, L, "ms-40-phone");
      });
    });
  });
}
