import { execSync } from "node:child_process";
import {
  expect,
  request as pwRequest,
  test,
  type APIRequestContext,
  type Browser,
  type Page,
} from "@playwright/test";
import { shot } from "./helpers";
import {
  Client,
  createProject,
  ensureAdmin,
  stackPassword,
  type Json,
} from "./stack";

/**
 * Подключённые Студии на живом стенде (docs/design/connected-devices.md): локальная Студия входит на сервер
 * кодом устройства, шлёт сигнал присутствия, а облако показывает её «в сети»; после остановки Студии и
 * окна присутствия показывает «не в сети» и «была в сети N минут назад».
 *
 * Нужны сервер с короткими интервалами (compose.smoke.yml: HSE_STUDIO__DEVICES__INTERVAL_S=10,
 * ONLINE_WINDOW_S=30) и локальная Студия `E2E_LOCAL_STUDIO_URL`. Остановить и поднять Студию тест может сам,
 * если заданы `E2E_LOCAL_STUDIO_STOP_CMD` и `E2E_LOCAL_STUDIO_START_CMD` (например, `docker stop/start …`);
 * без них вход на сервер отзывается на стороне облака, и Студия тоже перестаёт быть в сети.
 * Скриншоты: screenshots/ru/dv-*.png.
 */
const baseURL = process.env.E2E_BASE_URL ?? "http://localhost:17251";
const ORIGIN = new URL(baseURL).origin;
const LOCAL = process.env.E2E_LOCAL_STUDIO_URL ?? "";
const STOP_CMD = process.env.E2E_LOCAL_STUDIO_STOP_CMD ?? "";
const START_CMD = process.env.E2E_LOCAL_STUDIO_START_CMD ?? "";
const WINDOW_S = Number(process.env.E2E_PRESENCE_WINDOW_S ?? "30");
const RUN = Date.now().toString(36);
const ADMIN = {
  name: "Администратор Смоука",
  email: process.env.E2E_ADMIN_EMAIL ?? "admin@smoke.test",
};
const ANNA = { name: "Анна Петрова", email: `anna.${RUN}@dv.test` };
const DEVICE_NAME = `MacBook Анны ${RUN}`;

const log = (...parts: unknown[]): void => {
  console.log(`[dv ${new Date().toISOString().slice(11, 19)}]`, ...parts);
};

const newClient = async (): Promise<Client> =>
  new Client(await pwRequest.newContext({ baseURL }), ORIGIN);

const localStudio = async (): Promise<APIRequestContext> =>
  pwRequest.newContext({
    baseURL: LOCAL,
    extraHTTPHeaders: { Origin: new URL(LOCAL).origin },
  });

const withErrors = (page: Page): Page & { errors: string[] } => {
  const p = page as Page & { errors: string[] };
  p.errors = [];
  p.on("pageerror", (err) => p.errors.push(String(err)));
  return p;
};

const waitOperation = async (
  studio: APIRequestContext,
  id: string,
): Promise<Json> => {
  let last: Json = {};
  await expect
    .poll(
      async () => {
        last = (await (
          await studio.get(`/api/v1/git/operations/${id}`)
        ).json()) as Json;
        return String(last.state ?? last.status);
      },
      { timeout: 120_000, intervals: [500, 1_000, 2_000] },
    )
    .toMatch(/succeeded|success|done|completed|failed|error|cancelled/);
  return last;
};

/** Вход локальной Студии на сервер кодом устройства; человек подтверждает на /device в своём браузере. */
const studioLogin = async (
  browser: Browser,
  studio: APIRequestContext,
): Promise<string> => {
  const started = await studio.post("/api/v1/git/servers/login", {
    data: { server_url: baseURL, client_name: DEVICE_NAME },
  });
  expect(started.status(), await started.text()).toBe(200);
  const login = (await started.json()) as Json;
  const ctx = await browser.newContext({ baseURL, locale: "ru-RU" });
  const auth = await ctx.request.post("/api/v1/auth/login", {
    data: { email: ANNA.email, password: stackPassword() },
    headers: { Origin: ORIGIN },
  });
  expect(auth.status(), await auth.text()).toBe(200);
  const page = withErrors(await ctx.newPage());
  const approve = new URL(String(login.verification_uri_complete));
  await page.goto(approve.pathname + approve.search);
  await page.getByTestId("device-approve").click();
  await expect(page.getByTestId("device-result")).toHaveAttribute(
    "data-state",
    "approved",
  );
  await ctx.close();
  let credential = "";
  await expect
    .poll(
      async () => {
        const state = (await (
          await studio.get(
            `/api/v1/git/servers/login/${String(login.login_id)}`,
          )
        ).json()) as Json;
        credential = String(state.credential_id ?? "");
        return String(state.state);
      },
      { timeout: 60_000, intervals: [1_000, 2_000] },
    )
    .toBe("approved");
  return credential;
};

test.describe.configure({ mode: "serial" });

test.describe("подключённые Студии: присутствие в облаке и в локальной Студии", () => {
  let anna: Client;
  let project: { id: string; docId: string };
  let localProject = "";
  let credential = "";

  test("1. локальная Студия подключается, облако видит её в сети", async ({
    browser,
  }) => {
    test.skip(!LOCAL, "нужен E2E_LOCAL_STUDIO_URL");
    const admin = await newClient();
    if (process.env.E2E_ADMIN_EMAIL) {
      await admin.login(ADMIN.email, stackPassword());
    } else {
      await ensureAdmin(admin, ADMIN);
    }
    const invitation = await admin.json<{ link: string }>(
      await admin.post("/api/admin/invitations", {
        email: ANNA.email,
        ttl_days: null,
      }),
      201,
    );
    anna = await newClient();
    await anna.json(
      await anna.post("/api/v1/auth/register", {
        email: ANNA.email,
        name: ANNA.name,
        password: stackPassword(),
        invitation_token: invitation.link.split("/invite/")[1],
      }),
      200,
    );
    await anna.login(ANNA.email, stackPassword());
    project = await createProject(anna, `devices ${RUN}`);

    const studio = await localStudio();
    const profile = await studio.put("/api/v1/profile", {
      data: { name: ANNA.name, email: ANNA.email },
    });
    expect(profile.status(), await profile.text()).toBe(200);
    credential = await studioLogin(browser, studio);
    const opened = await studio.post(
      `/api/v1/git/servers/${credential}/projects/${project.id}/open`,
    );
    expect(opened.status(), await opened.text()).toBe(202);
    const operation = ((await opened.json()) as Json).operation_id;
    if (operation) await waitOperation(studio, String(operation));
    localProject = project.id;
    // Имя устройства по умолчанию заменяем понятным: так видно, что оно доходит до облака.
    const named = await studio.put("/api/v1/device", {
      data: { name: DEVICE_NAME },
    });
    expect(named.status(), await named.text()).toBe(200);

    await expect
      .poll(
        async () => {
          const list = (await (
            await anna.get("/api/v1/account/devices")
          ).json()) as { items: Json[] };
          const mine = list.items.find((d) => d.name === DEVICE_NAME);
          return mine ? String(mine.presence) : "none";
        },
        { timeout: 120_000, intervals: [2_000, 5_000] },
      )
      .toBe("online");
    log("облако видит Студию", DEVICE_NAME);

    const ctx = await browser.newContext({
      baseURL,
      locale: "ru-RU",
      viewport: { width: 1440, height: 900 },
    });
    await ctx.request.post("/api/v1/auth/login", {
      data: { email: ANNA.email, password: stackPassword() },
      headers: { Origin: ORIGIN },
    });
    const page = withErrors(await ctx.newPage());
    await page.goto(`/projects/${project.id}`);
    const badge = page.getByTestId("studio-presence");
    await expect(badge).toHaveAttribute("data-online", "true", {
      timeout: 60_000,
    });
    await expect(badge).toContainText("Студия в сети");
    await expect(badge).toContainText(DEVICE_NAME);
    await shot(page, "ru", "dv-01-cloud-badge-online");
    await badge.getByRole("button").click();
    const card = page.getByTestId("cloud-studios-panel").getByTestId("device-card");
    await expect(card).toBeVisible();
    await expect(card.getByTestId("device-name")).toContainText(DEVICE_NAME);
    await expect(card.getByTestId("device-project")).toBeVisible();
    await shot(page, "ru", "dv-02-cloud-panel");
    expect(page.errors).toEqual([]);
    await ctx.close();
    await studio.dispose();
  });

  test("2. в локальной Студии то же видно наоборот: облако в сети, что оно видит", async ({
    browser,
  }) => {
    test.skip(!LOCAL, "нужен E2E_LOCAL_STUDIO_URL");
    const ctx = await browser.newContext({
      baseURL: LOCAL,
      locale: "ru-RU",
      viewport: { width: 1440, height: 900 },
    });
    const page = withErrors(await ctx.newPage());
    await page.goto(`/projects/${localProject}`);
    const badge = page.getByTestId("studio-presence");
    await expect(badge).toHaveAttribute("data-online", "true", {
      timeout: 60_000,
    });
    await expect(badge).toContainText("Облако в сети");
    await badge.getByRole("button").click();
    const panel = page.getByTestId("local-link-panel");
    await expect(panel).toBeVisible();
    await expect(panel.getByTestId("link-cloud-sees")).toBeVisible();
    await expect(panel.getByTestId("link-last-sent")).toBeVisible();
    await shot(page, "ru", "dv-03-local-panel");
    expect(page.errors).toEqual([]);
    await ctx.close();
  });

  test("3. Студия остановлена: через окно присутствия облако показывает «не в сети» и «была в сети»", async ({
    browser,
  }) => {
    test.skip(!LOCAL, "нужен E2E_LOCAL_STUDIO_URL");
    test.setTimeout(10 * 60_000);
    if (STOP_CMD) {
      execSync(STOP_CMD, { stdio: "inherit" });
      log("Студия остановлена");
    } else {
      // Без команды остановки вход отзывается в облаке: сигнал больше не принимается.
      const tokens = await anna.json<Json[] | { items: Json[] }>(
        await anna.get("/api/v1/account/tokens"),
        200,
      );
      const list = Array.isArray(tokens) ? tokens : tokens.items;
      for (const token of list.filter((t) => t.origin === "device")) {
        await anna.delete(`/api/v1/account/tokens/${String(token.id)}`);
      }
      log("вход Студии отозван");
    }
    await new Promise((resolve) => setTimeout(resolve, (WINDOW_S + 15) * 1000));

    const ctx = await browser.newContext({
      baseURL,
      locale: "ru-RU",
      viewport: { width: 1440, height: 900 },
    });
    await ctx.request.post("/api/v1/auth/login", {
      data: { email: ANNA.email, password: stackPassword() },
      headers: { Origin: ORIGIN },
    });
    const page = withErrors(await ctx.newPage());
    await page.goto(`/projects/${project.id}`);
    const badge = page.getByTestId("studio-presence");
    await expect(badge).toHaveAttribute("data-online", "false", {
      timeout: 60_000,
    });
    await expect(badge).toContainText("Студия не в сети");
    await shot(page, "ru", "dv-04-cloud-badge-offline");
    await badge.getByRole("button").click();
    const card = page.getByTestId("cloud-studios-panel").getByTestId("device-card");
    await expect(card).toContainText(/была в сети/);
    await shot(page, "ru", "dv-05-cloud-panel-offline");
    const list = (await (
      await anna.get("/api/v1/account/devices")
    ).json()) as { items: Json[] };
    expect(list.items.find((d) => d.name === DEVICE_NAME)?.presence).toBe(
      "offline",
    );
    expect(page.errors).toEqual([]);
    await ctx.close();
    if (STOP_CMD && START_CMD) execSync(START_CMD, { stdio: "inherit" });
  });
});
