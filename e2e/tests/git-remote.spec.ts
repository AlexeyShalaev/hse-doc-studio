import { execFileSync } from "node:child_process";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
  expect,
  request as pwRequest,
  test,
  type Browser,
  type Page,
} from "@playwright/test";
import { LANGS, shot, type Lang } from "./helpers";
import {
  Client,
  createProject,
  ensureAdmin,
  stackPassword,
  type Json,
} from "./stack";

/**
 * Сервер как git-remote на живом стенде (12.6, п. 3): deploy/server + compose.smoke.yml.
 * Анна создаёт токен «Для git» в «Токенах», клонирует проект настоящим git с этой машины, отправляет
 * правку своей папки; push в чужую папку командного проекта отклоняется с текстом сервера; device flow:
 * тест начинает вход кодом, в браузере `/device?code=…` «Разрешить», опрос выдаёт токен, `git ls-remote`
 * с ним работает. Скриншоты ru/en: screenshots/<язык>/cf-git-*.png.
 */
const baseURL = process.env.E2E_BASE_URL ?? "http://localhost:17251";
const RUN = Date.now().toString(36);
const ADMIN = { name: "Администратор Смоука", email: "admin@smoke.test" };
const ANNA = { name: "Анна Петрова", email: `anna.${RUN}@git.test` };

const localeOf = (lang: Lang): string => (lang === "ru" ? "ru-RU" : "en-US");

const newClient = async (): Promise<Client> =>
  new Client(await pwRequest.newContext({ baseURL }), new URL(baseURL).origin);

const signedInPage = async (
  browser: Browser,
  lang: Lang,
  email: string,
): Promise<Page> => {
  const context = await browser.newContext({
    baseURL,
    locale: localeOf(lang),
    viewport: { width: 1440, height: 900 },
  });
  const res = await context.request.post("/api/v1/auth/login", {
    data: { email, password: stackPassword() },
    headers: { Origin: new URL(baseURL).origin },
  });
  expect(res.status()).toBe(200);
  return context.newPage();
};

/** git этой машины без чужих настроек и подсказок пароля. */
const git = (cwd: string, ...args: string[]): string =>
  execFileSync("git", ["-c", "credential.helper=", ...args], {
    cwd,
    encoding: "utf8",
    env: {
      PATH: process.env.PATH ?? "",
      HOME: cwd,
      GIT_TERMINAL_PROMPT: "0",
      GIT_CONFIG_NOSYSTEM: "1",
      GIT_AUTHOR_NAME: ANNA.name,
      GIT_AUTHOR_EMAIL: ANNA.email,
      GIT_COMMITTER_NAME: ANNA.name,
      GIT_COMMITTER_EMAIL: ANNA.email,
    },
    stdio: ["ignore", "pipe", "pipe"],
  });

const repoUrl = (projectId: string, token: string): string => {
  const url = new URL(`/git/${projectId}.git`, baseURL);
  url.username = "x";
  url.password = token;
  return url.toString();
};

test.describe.configure({ mode: "serial" });

test.describe("сервер как git-remote", () => {
  let anna: Client;
  let project: { id: string; docId: string };
  let gitToken = "";
  const work = mkdtempSync(join(tmpdir(), "cf-git-"));

  test.afterAll(() => {
    rmSync(work, { recursive: true, force: true });
  });

  test("1. токен «Для git» и «Клонировать с сервера» в настройках проекта", async ({
    browser,
  }) => {
    const admin = await newClient();
    await ensureAdmin(admin, ADMIN);
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
    project = await createProject(anna, `git-remote ${RUN}`);

    for (const lang of LANGS) {
      const page = await signedInPage(browser, lang, ANNA.email);
      await page.goto(`/projects/${project.id}/project-settings/sync`);
      await expect(page.getByTestId("project-git-remote")).toHaveAttribute(
        "data-state",
        "ready",
      );
      await shot(page, lang, "cf-git-01-clone-section");
      await page.goto("/settings/account?preset=git#account-tokens");
      await expect(page.getByTestId("token-form")).toBeVisible();
      await expect(page.getByTestId("token-scope-gitWrite")).toBeChecked();
      await shot(page, lang, "cf-git-02-token-preset");
      if (lang === "ru") {
        await page
          .getByRole("button", { name: /Создать|Create/ })
          .last()
          .click();
        const secret = (
          await page.getByTestId("token-created").textContent()
        )?.match(/hsd_pat_[A-Za-z0-9_-]+/)?.[0];
        expect(secret, "токен показан один раз").toBeTruthy();
        gitToken = secret ?? "";
      }
      await page.context().close();
    }
  });

  test("2. git clone, push своей правки, отказ в push новой ветки", async () => {
    git(work, "clone", repoUrl(project.id, gitToken), "repo");
    const repo = join(work, "repo");
    writeFileSync(join(repo, "notes-from-git.txt"), "правка из git\n");
    git(repo, "add", "-A");
    git(repo, "commit", "-m", "правка из git");
    git(repo, "push", "origin", "HEAD");
    const file = await anna.get(
      `/api/v1/projects/${project.id}/files/notes-from-git.txt`,
    );
    expect(file.status()).toBe(200);
    expect(await file.text()).toBe("правка из git\n");
    let refused = "";
    try {
      git(repo, "push", "origin", "HEAD:refs/heads/feature");
    } catch (err) {
      refused = String((err as { stderr?: string }).stderr ?? err);
    }
    expect(refused).toContain("ref_forbidden");
  });

  test("3. вход устройства кодом: /device «Разрешить», токен работает с git", async ({
    browser,
  }) => {
    const device = await newClient();
    const started = await device.json<Json>(
      await device.post("/api/v1/auth/device/code", {
        client_name: "Студия на MacBook Анны",
        client_kind: "desktop",
        scopes: ["git:read", "git:write"],
      }),
      200,
    );
    for (const lang of LANGS) {
      const page = await signedInPage(browser, lang, ANNA.email);
      await page.goto(`/device?code=${String(started.user_code)}`);
      await expect(page.getByTestId("device-card")).toBeVisible();
      await shot(page, lang, "cf-git-03-device");
      if (lang === "ru") {
        await page.getByTestId("device-approve").click();
        await expect(page.getByTestId("device-result")).toHaveAttribute(
          "data-state",
          "approved",
        );
        await shot(page, lang, "cf-git-04-device-approved");
      }
      await page.context().close();
    }
    let token = "";
    for (let attempt = 0; attempt < 10 && !token; attempt += 1) {
      await new Promise((resolve) => setTimeout(resolve, 5500));
      const res = await device.post("/api/v1/auth/device/token", {
        device_code: started.device_code,
      });
      if (res.status() === 200)
        token = String(((await res.json()) as Json).access_token);
    }
    expect(token).toMatch(/^hsd_pat_/);
    expect(git(work, "ls-remote", repoUrl(project.id, token))).toContain(
      "refs/heads/master",
    );
  });
});
