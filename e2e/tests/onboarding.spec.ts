import {
  expect,
  request as pwRequest,
  test,
  type Browser,
  type Page,
} from "@playwright/test";
import { shot } from "./helpers";
import { Client, ensureAdmin, stackPassword, type Json } from "./stack";

/**
 * Онбординг на живом стенде deploy/server: анкета, экскурсия по главной, демо-проект в песочнице
 * (весь сценарий без раннеров и ИИ: сборка, агент, замечания и git изображены во вкладке) и итог;
 * пропуск и демо из меню «Справка». Под Playwright тур сам не всплывает (navigator.webdriver),
 * поэтому сценарий включает автозапуск флагом в localStorage.
 *
 * Скриншоты: screenshots/<язык>/ob-*.png.
 */
const baseURL = process.env.E2E_BASE_URL ?? "http://localhost:17251";
const ORIGIN = new URL(baseURL).origin;
const ADMIN = { name: "Администратор Смоука", email: "admin@smoke.test" };

test.describe.configure({ mode: "serial" });

const openAs = async (browser: Browser, locale: string) => {
  const api = new Client(await pwRequest.newContext({ baseURL }), ORIGIN);
  await ensureAdmin(api, ADMIN);
  const context = await browser.newContext({
    baseURL,
    locale,
    viewport: { width: 1440, height: 960 },
  });
  await context.addInitScript(() => {
    window.localStorage.setItem("hds.onboarding.autostart", "on");
  });
  const session = new Client(context.request, ORIGIN);
  await session.login(ADMIN.email, stackPassword());
  await session.json(await session.post("/api/v1/onboarding/reset"), 200);
  return { page: await context.newPage(), session };
};

const statusOf = async (session: Client): Promise<string> =>
  String(
    (await session.json<Json>(await session.get("/api/v1/onboarding"), 200))
      .status,
  );

/** Жмёт главную кнопку подсказки, пока тур не кончится: на шагах демо она выполняет действие. */
const walkTour = async (page: Page, until: () => Promise<boolean>) => {
  for (let i = 0; i < 40; i++) {
    if (await until()) return;
    const overlay = page.getByTestId("tour-overlay");
    await expect(overlay).toBeVisible();
    const step = await overlay.getAttribute("data-tour-step");
    const next = page.getByTestId("tour-next");
    await expect(next).toBeEnabled({ timeout: 15_000 });
    await next.click();
    await expect
      .poll(
        async () =>
          (await until()) ||
          (await overlay
            .getAttribute("data-tour-step", { timeout: 1000 })
            .catch(() => null)) !== step,
        { timeout: 20_000 },
      )
      .toBe(true);
  }
  throw new Error("тур не закончился за 40 шагов");
};

test("онбординг (ru): анкета, экскурсия, демо-проект и итог", async ({
  browser,
}) => {
  test.setTimeout(3 * 60_000);
  const { page, session } = await openAs(browser, "ru-RU");

  await page.goto("/");
  await expect(page.getByTestId("onboarding-intro")).toBeVisible();
  await shot(page, "ru", "ob-01-intro");
  await page.getByTestId("onboarding-start").click();
  await page.getByTestId("onboarding-answer-role-student").click();
  await page.getByTestId("onboarding-answer-work-other").click();
  await page.getByTestId("onboarding-answer-latex-none").click();
  await page.getByTestId("onboarding-answer-git-none").click();

  await expect(page.getByTestId("tour-overlay")).toHaveAttribute(
    "data-tour-step",
    "home.new-project",
  );
  await expect(page.getByTestId("tour-spotlight")).toBeVisible();
  await shot(page, "ru", "ob-02-tour");
  await walkTour(page, async () => page.url().includes("/onboarding/demo"));

  await expect(page.getByTestId("demo-sandbox")).toBeVisible();
  await shot(page, "ru", "ob-03-demo");
  const finish = page.getByTestId("onboarding-finish");
  await walkTour(page, () => finish.isVisible());
  await shot(page, "ru", "ob-04-finish");
  // Итог спрашивает сервер, живы ли общие раннеры: ответ «доступна» или «недоступна», не догадка.
  await expect(page.getByTestId("onboarding-build-note")).toHaveAttribute(
    "data-availability",
    /^(available|unavailable)$/,
  );

  const answers = (
    await session.json<Json>(await session.get("/api/v1/onboarding"), 200)
  ).answers as Json;
  expect(answers).toEqual({
    role: "student",
    work: "other",
    latex: "none",
    git: "none",
  });
  await page.getByTestId("onboarding-finish-later").click();
  await expect.poll(() => statusOf(session)).toBe("completed");

  await page.reload();
  await expect(page.getByTestId("onboarding-intro")).toBeHidden();
});

test("онбординг (en): пропуск и демо-проект из меню «Справка»", async ({
  browser,
}) => {
  const { page, session } = await openAs(browser, "en-US");

  await page.goto("/");
  await expect(page.getByTestId("onboarding-intro")).toBeVisible();
  await page.getByTestId("onboarding-skip").click();
  await expect(page.getByTestId("onboarding-intro")).toBeHidden();
  await expect.poll(() => statusOf(session)).toBe("skipped");

  await page.getByTestId("help-menu-trigger").click();
  await page.getByTestId("help-menu-demo").click();
  await expect(page).toHaveURL(/\/onboarding\/demo/);
  await expect(page.getByTestId("tour-overlay")).toHaveAttribute(
    "data-tour-step",
    "demo.intro",
  );
  await page.getByTestId("tour-next").click();
  await page.getByTestId("demo-create-project").click();
  await expect(page.getByTestId("demo-editor")).toBeVisible();
  await shot(page, "en", "ob-05-demo-help");
  await page.keyboard.press("Escape");
  await expect(page.getByTestId("tour-overlay")).toBeHidden();
  await page.getByTestId("demo-exit").click();
  await expect(page).toHaveURL(/\/$/);
});
