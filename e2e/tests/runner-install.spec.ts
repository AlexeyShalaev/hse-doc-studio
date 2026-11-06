import { expect, test, type Page } from "@playwright/test";
import { LANGS, shot, type Lang } from "./helpers";
import { loginOnPhone } from "./phoneHelpers";

/**
 * Команды установки раннера у токена (стенд server-lite, админ из окружения): после создания токена админ видит
 * секрет один раз и три способа запуска, копирует команду кнопкой и может прочитать скрипт установки до запуска.
 * Скрипт отдаётся без секретов, секрет есть только в команде. Ru и en.
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

const openSecret = async (page: Page, label: string): Promise<void> => {
  await loginOnPhone(page, ADMIN_EMAIL, adminPassword());
  await page.goto("/admin/runners");
  await page.getByTestId("runner-token-create").click();
  await page.getByTestId("token-label").fill(label);
  await page.getByTestId("token-create-submit").click();
  await expect(page.getByTestId("secret-once")).toBeVisible();
};

for (const lang of LANGS) {
  test.describe(`Команда установки раннера [${lang}]`, () => {
    test.use({
      locale: lang === "ru" ? "ru-RU" : "en-US",
      permissions: ["clipboard-read", "clipboard-write"],
    });
    const L = lang as Lang;

    test("токен: вкладки docker и скрипт, копирование, скрипт без секретов", async ({
      page,
      browser,
    }) => {
      await openSecret(page, `e2e-install-${lang}`);
      const origin = new URL(page.url()).origin;

      // Docker: одна строка с адресом Студии и токеном.
      const docker = page.getByTestId("runner-command-docker");
      await expect(docker).toContainText("docker run");
      await expect(docker).toContainText(`HSE_RUNNER__API_URL=${origin}`);
      await docker.getByRole("button").first().click();
      const dockerCopied = await page.evaluate(() =>
        navigator.clipboard.readText(),
      );
      expect(dockerCopied).toContain("docker run");
      expect(dockerCopied).toMatch(/HSE_RUNNER__TOKEN=hsrt_/);

      // Скрипт: Linux с sudo, macOS без него.
      await page.getByTestId("runner-how-script").click();
      const script = page.getByTestId("runner-command-script");
      await expect(script).toContainText("/api/runner/v1/install.sh");
      await expect(script).toContainText("sudo env");
      await shot(page, L, "runner-install-script");
      await script.getByRole("button").first().click();
      const copied = await page.evaluate(() => navigator.clipboard.readText());
      expect(copied).toMatch(/^curl -fsSL .*install\.sh \| sudo env /);
      expect(copied).toMatch(/hsrt_/);
      await page.getByTestId("runner-script-os-macos").click();
      await expect(script).not.toContainText("sudo");

      // Сам скрипт читается без входа и не содержит секретов.
      const anon = await browser.newContext({ baseURL: origin });
      const response = await anon.request.get("/api/runner/v1/install.sh");
      expect(response.status()).toBe(200);
      const text = await response.text();
      expect(text.startsWith("#!/bin/sh")).toBe(true);
      expect(text).toContain("uninstall");
      expect(text).not.toMatch(/hsrt_/);
      await anon.close();
    });

    test("SSH: адреса внутренней сети и метаданных облака закрыты защитой, пароль нигде не виден", async ({
      page,
    }) => {
      await loginOnPhone(page, ADMIN_EMAIL, adminPassword());
      await page.goto("/admin/runners");
      await page.getByTestId("runner-install-open").click();
      await page.getByTestId("install-ssh-open").click();

      for (const host of ["10.0.0.5", "169.254.169.254", "127.0.0.1"]) {
        await page.getByTestId("ssh-host").fill(host);
        await page.getByTestId("ssh-username").fill("deploy");
        await page.getByTestId("ssh-password").fill("e2e-canary-password");
        await page.getByTestId("ssh-probe-submit").click();
        const error = page.getByTestId("ssh-error");
        await expect(error).toBeVisible();
        await expect(page.getByTestId("ssh-fingerprint")).toHaveCount(0);
        expect(await page.content()).not.toContain("e2e-canary-password");
        await page.getByTestId("ssh-host").fill("");
      }
      await shot(page, L, "runner-install-ssh-blocked");
    });

    test("токен на телефоне: ничего не обрезано", async ({ page }) => {
      await page.setViewportSize({ width: 360, height: 740 });
      await openSecret(page, `e2e-install-phone-${lang}`);
      await page.getByTestId("runner-how-script").click();
      const box = await page.getByTestId("runner-command-script").boundingBox();
      expect(box).not.toBeNull();
      expect((box?.x ?? 0) + (box?.width ?? 0)).toBeLessThanOrEqual(360);
      await shot(page, L, "runner-install-phone");
    });
  });
}
