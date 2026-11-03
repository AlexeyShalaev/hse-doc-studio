import {
  expect,
  test,
  type Browser,
  type CDPSession,
  type Page,
} from "@playwright/test";
import { LANGS, USERS, login, logout, shot, type Lang } from "./helpers";

/**
 * Passkey на стенде server-lite с виртуальным аутентификатором Chrome (CDP WebAuthn): человек добавляет ключ
 * в «Аккаунте», выходит и входит кнопкой «Войти с passkey» без пароля; второй раз тот же ключ не добавляется;
 * на ru админ видит ключ в карточке человека и сбрасывает его, после чего вход ключом отклоняется; на en человек
 * удаляет ключ сам. Адрес стенда http://localhost:8100: для WebAuthn localhost считается защищённым контекстом.
 */

const PERSON: Record<Lang, string> = {
  ru: USERS.anna.email,
  en: USERS.victor.email,
};
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

type VirtualKey = { cdp: CDPSession; authenticatorId: string };

/** Платформенный аутентификатор с биометрией: ключи обнаруживаемые, присутствие и UV подтверждаются сами. */
const attachAuthenticator = async (page: Page): Promise<VirtualKey> => {
  const cdp = await page.context().newCDPSession(page);
  await cdp.send("WebAuthn.enable");
  const { authenticatorId } = await cdp.send(
    "WebAuthn.addVirtualAuthenticator",
    {
      options: {
        protocol: "ctap2",
        transport: "internal",
        hasResidentKey: true,
        hasUserVerification: true,
        isUserVerified: true,
        automaticPresenceSimulation: true,
      },
    },
  );
  return { cdp, authenticatorId };
};

const storedKeys = async (key: VirtualKey) =>
  (
    await key.cdp.send("WebAuthn.getCredentials", {
      authenticatorId: key.authenticatorId,
    })
  ).credentials;

const newPage = async (browser: Browser, lang: Lang): Promise<Page> => {
  const context = await browser.newContext({
    locale: lang === "ru" ? "ru-RU" : "en-US",
  });
  return context.newPage();
};

const openPasskeys = async (page: Page): Promise<void> => {
  await page.goto("/settings/account");
  await expect(page.getByTestId("account-passkeys")).toBeVisible();
  await expect(page.getByTestId("passkeys-loading")).toHaveCount(0);
};

/** Настройки открыты окном поверх приложения: меню аккаунта за ним, поэтому окно закрываем. */
const closeSettings = async (page: Page): Promise<void> => {
  await page.locator(".settings-modal-close").click();
  await expect(page.getByTestId("account-passkeys")).toHaveCount(0);
};

const keyRows = (page: Page) =>
  page.getByTestId("account-passkeys").locator("[data-testid^=passkey-item-]");

/**
 * Вход по ключу. Виртуальный аутентификатор сам отвечает на ожидающий запрос автозаполнения поля логина
 * (conditional UI), поэтому вход нередко случается без кнопки; иначе жмём «Войти с passkey».
 */
const signInWithPasskey = async (page: Page): Promise<void> => {
  const menu = page.getByTestId("account-menu-trigger");
  const button = page.getByTestId("login-passkey");
  await expect(menu.or(button)).toBeVisible();
  // Кнопка может исчезнуть посреди щелчка, если автозаполнение успело раньше.
  if (await button.isVisible())
    await button.click({ timeout: 5_000 }).catch(() => undefined);
  await expect(menu).toBeVisible();
  await expect(page.locator("input[type=password]")).toHaveCount(0);
};

test.describe.configure({ timeout: 120_000 });

for (const lang of LANGS) {
  test(`passkey: добавить, войти без пароля и убрать (${lang})`, async ({
    browser,
  }) => {
    const page = await newPage(browser, lang);
    const key = await attachAuthenticator(page);
    const email = PERSON[lang];

    await login(page, email);
    await openPasskeys(page);
    const before = await keyRows(page).count();

    // Сразу после входа подтверждать личность не нужно: окно свежей сессии открыто.
    await page.getByTestId("passkey-add").click();
    await expect(keyRows(page)).toHaveCount(before + 1);
    const stored = await storedKeys(key);
    expect(stored).toHaveLength(1);
    expect(stored[0]?.isResidentCredential).toBe(true);
    expect(stored[0]?.rpId).toBe("localhost");
    await shot(page, lang, "passkeys-01-added");

    // Тот же аутентификатор второй раз ключ не создаёт: сервер прислал его в excludeCredentials.
    await page.getByTestId("passkey-add").click();
    await expect(page.getByTestId("passkeys-failure")).toBeVisible();
    await expect(keyRows(page)).toHaveCount(before + 1);
    expect(await storedKeys(key)).toHaveLength(1);

    await closeSettings(page);
    await logout(page);
    await expect(page.locator("input[type=email]")).toHaveAttribute(
      "autocomplete",
      "username webauthn",
    );
    await shot(page, lang, "passkeys-02-login");
    await signInWithPasskey(page);
    await shot(page, lang, "passkeys-03-signed-in");

    await openPasskeys(page);
    const row = keyRows(page).last();
    await expect(row).toBeVisible();
    const id = (await row.getAttribute("data-testid"))?.replace(
      "passkey-item-",
      "",
    );
    expect(id).toBeTruthy();

    if (lang === "ru") {
      // Админ видит ключ в карточке человека и сбрасывает все его ключи.
      const admin = await newPage(browser, lang);
      await admin.goto("/");
      await admin.locator("input[type=email]").fill(ADMIN_EMAIL);
      await admin.locator("input[type=password]").fill(adminPassword());
      await admin
        .getByTestId("login-form")
        .locator("button[type=submit]")
        .click();
      await expect(admin.getByTestId("account-menu-trigger")).toBeVisible();
      const found = await admin.request.get(
        `/api/admin/users?q=${encodeURIComponent(email)}`,
      );
      expect(found.status()).toBe(200);
      const person = ((await found.json()) as { items: { id: string }[] })
        .items[0];
      expect(person).toBeTruthy();
      await admin.goto(`/admin/users?user=${person?.id ?? ""}`);
      await expect(admin.getByTestId("person-passkeys")).toBeVisible();
      await expect(admin.getByTestId("person-passkeys-count")).toContainText(
        String(before + 1),
      );
      await shot(admin, lang, "passkeys-04-admin-person");
      await admin.getByTestId("person-passkeys-reset").click();
      await admin.getByTestId("person-passkeys-reset-confirm").click();
      await expect(
        admin.locator(
          '[data-testid^="person-passkey-"]:not([data-testid^="person-passkeys"])',
        ),
      ).toHaveCount(0);
      const after = await admin.request.get(
        `/api/admin/users/${person?.id ?? ""}/passkeys`,
      );
      expect(await after.json()).toEqual({ items: [] });
      await admin.context().close();

      // Ключ остался в аутентификаторе, но сервер его больше не знает: вход отклоняется.
      await closeSettings(page);
      await logout(page);
      await page.getByTestId("login-passkey").click();
      await expect(page.getByTestId("login-error")).toBeVisible();
      await expect(page.getByTestId("account-menu-trigger")).toHaveCount(0);
      await shot(page, lang, "passkeys-05-key-reset");
    } else {
      // Человек удаляет ключ сам; пароль остаётся, поэтому это не последний способ войти.
      await page.getByTestId(`passkey-delete-${id ?? ""}`).click();
      await page.getByTestId("passkey-delete-confirm").click();
      await expect(keyRows(page)).toHaveCount(before);
      await shot(page, lang, "passkeys-04-removed");
    }

    await page.context().close();
  });
}
