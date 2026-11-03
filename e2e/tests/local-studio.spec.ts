import { expect, test, type Page } from "@playwright/test";
import { LANGS, USERS, login, shot } from "./helpers";

/**
 * «Локальная версия» облачной Студии на стенде server-lite (docs/design/local-from-cloud.md):
 * экран открывается из меню аккаунта, в команде установки адрес этого сервера, кнопка копирует её,
 * «Подключить локальную Студию» и «Открыть в локальной Студии» ведут на localhost с сервером и проектом.
 * Скриншоты ru/en: screenshots/<язык>/ls-*.png.
 */
const COPY = { ru: "Копировать", en: "Copy" } as const;
const COMMAND = { ru: "Команда установки", en: "Install command" } as const;
const MENU = { ru: "Локальная версия", en: "Local version" } as const;

const commandField = (page: Page, lang: (typeof LANGS)[number]) =>
  page
    .getByTestId("local-studio-install-command")
    .getByLabel(COMMAND[lang]);

/** Свой проект Анны: из демо-данных, а если их нет, создаётся тут же. */
const ownProject = async (page: Page, lang: string): Promise<string> => {
  const list = (await (
    await page.request.get("/api/v1/projects?limit=1")
  ).json()) as { items: { id: string }[] };
  const found = list.items[0]?.id;
  if (found) return found;
  const boot = (await (
    await page.request.get("/api/v1/session/bootstrap")
  ).json()) as { csrf_token: string };
  const created = await page.request.post("/api/v1/projects", {
    data: {
      name: `E2E локальная версия ${lang}`,
      pack_id: "hse-cs-sse",
      template_id: "coursework",
      version: "2026.1",
      lang: "ru",
      authors: [{ name: "Анна Иванова" }],
    },
    headers: {
      "X-CSRF-Token": boot.csrf_token,
      Origin: new URL(page.url()).origin,
    },
  });
  expect(created.status()).toBe(201);
  return ((await created.json()) as { id: string }).id;
};

for (const lang of LANGS) {
  test.describe(`Локальная версия [${lang}]`, () => {
    test.use({
      locale: lang === "ru" ? "ru-RU" : "en-US",
      permissions: ["clipboard-read", "clipboard-write"],
    });

    test("экран из меню, команды с адресом сервера и копирование", async ({
      page,
      baseURL,
    }) => {
      await login(page, USERS.anna.email);
      const info = (await (
        await page.request.get("/api/v1/local-studio")
      ).json()) as {
        server_url: string;
        server_version: string;
        install_base_url: string;
      };
      expect(info.server_url).toBe(new URL(baseURL ?? "").origin);

      await page.getByTestId("account-menu-trigger").click();
      await page.getByTestId("account-menu-local-studio").click();
      await expect(page).toHaveURL(/\/local-studio$/);
      await expect(page.getByTestId("local-studio-guide")).toBeVisible();
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible();

      await page.getByTestId("local-studio-os-macos").click();
      const field = commandField(page, lang);
      await expect(field).toHaveValue(
        `curl -fsSL ${info.install_base_url}/install.sh | HSE_STUDIO_LANG=${lang} HSE_STUDIO_CONNECT='${info.server_url}' sh`,
      );
      await page
        .getByTestId("local-studio-install-command")
        .getByRole("button", { name: COPY[lang] })
        .click();
      const copied = await page.evaluate(() => navigator.clipboard.readText());
      expect(copied).toBe(await field.inputValue());
      await shot(page, lang, "ls-01-guide");

      await page.getByTestId("local-studio-os-windows").click();
      await expect(field).toHaveValue(/install\.ps1 \| iex$/);
      await page.getByTestId("local-studio-pin").check();
      await expect(field).toHaveValue(/\$env:TAG='\d+\.\d+'/);

      await page.getByTestId("local-studio-port").fill("17245");
      const connect = page.getByTestId("open-in-local-studio");
      const href = new URL((await connect.getAttribute("href")) ?? "");
      expect(href.origin).toBe("http://localhost:17245");
      expect(href.pathname).toBe("/connect");
      expect(href.searchParams.get("server")).toBe(info.server_url);
      await shot(page, lang, "ls-02-connect");
    });

    test("проект: «Открыть в локальной Студии» с id проекта", async ({
      page,
    }) => {
      await login(page, USERS.anna.email);
      const projectId = await ownProject(page, lang);

      await page.goto(`/local-studio?project=${projectId}`);
      const block = page.getByTestId("local-studio-project");
      await expect(block).toBeVisible();
      const open = block.getByTestId("open-in-local-studio");
      const href = new URL((await open.getAttribute("href")) ?? "");
      expect(href.searchParams.get("project")).toBe(projectId);
      await expect(block.getByRole("textbox").first()).toHaveValue(
        new RegExp(`/git/${projectId}\\.git$`),
      );
      await shot(page, lang, "ls-03-project");

      await page.goto(`/projects/${projectId}/project-settings/sync`);
      await expect(
        page.getByTestId("project-git-remote").getByTestId("open-in-local-studio"),
      ).toHaveAttribute("href", new RegExp(`project=${projectId}`), {
        // Ссылка появляется после ответа /local-studio; настройки проекта грузят много запросов разом.
        timeout: 30_000,
      });
      await expect(page.getByText(MENU[lang]).first()).toBeVisible();
    });
  });
}
