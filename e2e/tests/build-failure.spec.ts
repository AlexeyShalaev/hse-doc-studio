import {
  expect,
  request as pwRequest,
  test,
  type APIRequestContext,
  type Page,
} from "@playwright/test";
import { shot } from "./helpers";
import {
  Client,
  TERMINAL,
  createProject,
  ensureAdmin,
  stackPassword,
  stackSh,
  triggerCompile,
  waitCompile,
  type Json,
} from "./stack";

/**
 * Упавшая сборка объясняет себя (docs/workbench/compile.md, «Если сборка не удалась»): ломаем документ ошибкой
 * LaTeX, собираем в облаке на личном раннере Анны и, если задана локальная Студия, у неё самой, и видим во
 * вкладке «Сборка» плашку с кодом и текстом «что делать», журнал с ошибкой LaTeX и причину в списке документов.
 *
 * Стенд: deploy/server + compose.smoke.yml + compose.personal.yml (stack.sh up). Локальная Студия того же
 * образа в режиме local: E2E_LOCAL_STUDIO_URL (без неё локальная часть пропускается).
 * Скриншоты: screenshots/<язык>/bf-*.png.
 */
const baseURL = process.env.E2E_BASE_URL ?? "http://localhost:17251";
const LOCAL = process.env.E2E_LOCAL_STUDIO_URL ?? "";
const RUN = Date.now().toString(36);
const ADMIN = { name: "Администратор Смоука", email: "admin@smoke.test" };
const ANNA = { name: "Анна Петрова", email: `anna.${RUN}@failure.test` };
const BROKEN =
  "\\documentclass{article}\n\\begin{document}\n\\undefinedcommandforfailure\n\\end{document}\n";

const newClient = async (): Promise<Client> =>
  new Client(await pwRequest.newContext({ baseURL }), new URL(baseURL).origin);

const compilePane = (project: { id: string; docId: string }): string =>
  `/projects/${project.id}/documents/${project.docId}?tab=compile`;

const signedIn = async (
  browser: import("@playwright/test").Browser,
  email: string,
): Promise<Page> => {
  const context = await browser.newContext({
    baseURL,
    locale: "ru-RU",
    viewport: { width: 1440, height: 900 },
  });
  const res = await context.request.post("/api/v1/auth/login", {
    data: { email, password: stackPassword() },
    headers: { Origin: new URL(baseURL).origin },
  });
  expect(res.status()).toBe(200);
  return context.newPage();
};

const sourceOf = async (
  client: Client,
  project: { id: string; docId: string },
): Promise<string> => {
  const doc = await client.json<{ source_file: string }>(
    await client.get(
      `/api/v1/projects/${project.id}/documents/${project.docId}`,
    ),
    200,
  );
  return doc.source_file;
};

test.describe.configure({ mode: "serial" });

test.describe("упавшая сборка объясняет себя", () => {
  let anna: Client;
  let project: { id: string; docId: string };

  test("1. облако: личный раннер Анны, ошибка LaTeX видна плашкой, журналом и в списке документов", async ({
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
    const token = await anna.json<{ secret: string }>(
      await anna.post("/api/v1/account/runner-tokens", {
        label: "bf",
        ttl_hours: 24,
      }),
      201,
    );
    try {
      stackSh("personal-stop");
    } catch {
      // Раннера ещё нет.
    }
    stackSh("personal-reset");
    stackSh("personal-up", token.secret);
    await expect
      .poll(
        async () =>
          String(
            (
              (
                await anna.json<Json[]>(
                  await anna.get("/api/v1/account/runners"),
                  200,
                )
              ).find((r) => !r.revoked) ?? {}
            ).state,
          ),
        { timeout: 120_000 },
      )
      .toBe("online");

    project = await createProject(anna, `Сбой сборки ${RUN}`);
    const source = await sourceOf(anna, project);
    expect(
      (
        await anna.putText(
          `/api/v1/projects/${project.id}/files/${source}`,
          BROKEN,
        )
      ).status(),
    ).toBeLessThan(300);

    const page = await signedIn(browser, ANNA.email);
    await page.goto(compilePane(project));
    await page
      .getByRole("button", { name: /Запустить xelatex|Пересобрать/ })
      .first()
      .click();

    const notice = page.getByTestId("compile-failure");
    await expect(notice).toBeVisible({ timeout: 8 * 60_000 });
    await expect(notice).toHaveAttribute("data-code", "build_failed");
    await expect(page.getByTestId("compile-failure-message")).toContainText(
      "LaTeX",
    );
    // Журнал не пуст: вывод latexmk с самой ошибкой и строка причины в конце.
    await expect(
      page.getByText("Undefined control sequence").first(),
    ).toBeVisible();
    await expect(page.getByText(/\[error\] build_failed:/)).toBeVisible();
    await shot(page, "ru", "bf-01-cloud-tab");

    // Та же запись по API: код, текст и журнал не пусты, место сборки личный раннер.
    const compileId = String(
      (
        await anna.json<{ last_compile_id: string }>(
          await anna.get(
            `/api/v1/projects/${project.id}/documents/${project.docId}`,
          ),
          200,
        )
      ).last_compile_id,
    );
    const record = await waitCompile(
      anna,
      project.id,
      project.docId,
      compileId,
      (view) => TERMINAL.has(view.status),
      60_000,
    );
    expect(record.status).toBe("failure");
    const detail = await anna.json<{
      log: string;
      error: { code: string; message: string };
      placement: { state: string };
    }>(
      await anna.get(
        `/api/v1/projects/${project.id}/documents/${project.docId}/compiles/${compileId}`,
      ),
      200,
    );
    expect(detail.placement.state).toBe("personal");
    expect(detail.error.code).toBe("build_failed");
    expect(detail.log).toContain("Undefined control sequence");

    // Список документов: причина под названием и в блоке «Сейчас».
    await page.goto(`/projects/${project.id}`);
    await expect(
      page.getByTestId(`doc-failure-${project.docId}`),
    ).toBeVisible();
    await expect(page.getByTestId("now-reason").first()).toBeVisible();
    await shot(page, "ru", "bf-02-cloud-list");
    await page.context().close();
  });

  test("2. облако: раннер без образа TeX объясняет отказ, а не молчит", async ({
    browser,
  }) => {
    // Общий раннер стенда без образа отвечает image_missing; в CI образ есть, поэтому проверяем только форму ответа.
    const record = await (async () => {
      const compileId = await triggerCompile(anna, project.id, project.docId);
      return waitCompile(
        anna,
        project.id,
        project.docId,
        compileId,
        (v) => TERMINAL.has(v.status),
        8 * 60_000,
      );
    })();
    const detail = await anna.json<{
      log: string;
      error: { code: string; message: string } | null;
    }>(
      await anna.get(
        `/api/v1/projects/${project.id}/documents/${project.docId}/compiles/${record.id}`,
      ),
      200,
    );
    expect(record.status).toBe("failure");
    expect(detail.error?.code).toBeTruthy();
    expect(detail.error?.message.length ?? 0).toBeGreaterThan(20);
    expect(detail.log.trim().length).toBeGreaterThan(0);
    void browser;
  });

  test("3. локальная Студия: «Собрать» оставляет запись с журналом и причиной", async ({
    browser,
  }) => {
    test.skip(!LOCAL, "нужен E2E_LOCAL_STUDIO_URL");
    const studio: APIRequestContext = await pwRequest.newContext({
      baseURL: LOCAL,
      extraHTTPHeaders: { Origin: new URL(LOCAL).origin },
    });
    const boot = (await (
      await studio.get("/api/v1/session/bootstrap")
    ).json()) as { csrf_token?: string };
    const csrf = boot.csrf_token ?? "";
    const created = await studio.post("/api/v1/projects", {
      data: {
        name: `Локальный сбой ${RUN}`,
        pack_id: "hse-cs-sse",
        template_id: "coursework",
        version: "2026.1",
        lang: "ru",
        authors: [{ name: "Анна Петрова" }],
      },
      headers: { "X-CSRF-Token": csrf },
    });
    expect(created.status(), await created.text()).toBe(201);
    const local = (await created.json()) as { id: string };
    const docs = (await (
      await studio.get(`/api/v1/projects/${local.id}/documents`)
    ).json()) as {
      id: string;
      source_file: string;
    }[];
    const doc = docs[0]!;
    const put = await studio.put(
      `/api/v1/projects/${local.id}/files/${doc.source_file}`,
      {
        data: BROKEN,
        headers: { "X-CSRF-Token": csrf, "Content-Type": "text/plain" },
      },
    );
    expect(put.status()).toBeLessThan(300);

    const context = await browser.newContext({
      baseURL: LOCAL,
      locale: "ru-RU",
      viewport: { width: 1440, height: 900 },
    });
    const page = await context.newPage();
    await page.goto(`/projects/${local.id}/documents/${doc.id}?tab=compile`);
    await page
      .getByRole("button", { name: /Запустить xelatex|Пересобрать/ })
      .first()
      .click();

    // Образ или Docker могут отсутствовать на машине: тогда причиной будет отказ окружения, но объяснена она так же.
    const notice = page.getByTestId("compile-failure");
    await expect(notice).toBeVisible({ timeout: 10 * 60_000 });
    await expect(page.getByTestId("compile-failure-code")).toHaveText(
      /build_failed|image_missing|docker_unavailable|idle_timeout/,
    );
    await expect(page.getByTestId("compile-failure-message")).not.toBeEmpty();
    await shot(page, "ru", "bf-03-local-tab");

    const list = (await (
      await studio.get(
        `/api/v1/projects/${local.id}/documents/${doc.id}/compiles`,
      )
    ).json()) as {
      id: string;
      status: string;
      error: { code: string } | null;
    }[];
    expect(list.length).toBeGreaterThan(0);
    expect(list.at(-1)?.status).toBe("failure");
    expect(list.at(-1)?.error?.code).toBeTruthy();
    const record = (await (
      await studio.get(
        `/api/v1/projects/${local.id}/documents/${doc.id}/compiles/${list.at(-1)!.id}`,
      )
    ).json()) as { log: string };
    expect(record.log.trim().length).toBeGreaterThan(0);
    await context.close();
  });
});
