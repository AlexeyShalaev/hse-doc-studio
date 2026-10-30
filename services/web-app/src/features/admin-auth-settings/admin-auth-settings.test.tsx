import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  cleanup,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { I18nextProvider } from "react-i18next";
import { MemoryRouter } from "react-router";
import { afterEach, beforeAll, beforeEach, describe, expect, it } from "vitest";
import { i18n } from "@shared/lib";
import { createDemoRouter } from "@shared/api/demo";
import type { DemoRequest } from "@shared/api/demo";
import {
  AdminAuthSettingsSchema,
  AdminOidcProviderPageSchema,
  AdminRegistrationSettingsSchema,
  AdminSmtpSettingsSchema,
} from "@entities/session";
import { installServerDemo } from "@/app/demo";
import { activateServerScenario } from "@/app/demo/server";
import { serverAdminDemoRoutes } from "@/app/demo/server/routes";
import { AdminAuthSettings } from "./index";
import { validateOidc, emptyOidcDraft, parseDomains } from "./lib/validate";

// Настройки входа поверх демо-транспорта: те же запросы, что уйдут настоящему
// бэкенду, и ответы, проходящие те же схемы.

const mount = (entry = "/admin/settings") =>
  render(
    <I18nextProvider i18n={i18n}>
      <QueryClientProvider
        client={
          new QueryClient({
            defaultOptions: {
              queries: { retry: false },
              mutations: { retry: false },
            },
          })
        }
      >
        <MemoryRouter initialEntries={[entry]}>
          <AdminAuthSettings />
        </MemoryRouter>
      </QueryClientProvider>
    </I18nextProvider>,
  );

const router = createDemoRouter(serverAdminDemoRoutes);
const call = async (
  method: DemoRequest["method"],
  path: string,
  body?: unknown,
) => {
  const found = router.match(method, path);
  if (!found) throw new Error(`no demo route ${method} ${path}`);
  return found.handler({
    method,
    path,
    params: found.params,
    query: {},
    body,
    forward: () => Promise.reject(new Error("forward")),
  });
};

const openMenu = async (
  user: ReturnType<typeof userEvent.setup>,
  name: string,
) => {
  await user.click(
    await screen.findByRole("button", {
      name: `Действия с провайдером ${name}`,
    }),
  );
};

describe("настройки входа в админке", () => {
  beforeAll(() => {
    installServerDemo();
  });
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
    activateServerScenario("admin_ready");
  });
  afterEach(cleanup);

  it("ответы демо проходят схемы контракта и не содержат секретов", async () => {
    AdminRegistrationSettingsSchema.parse(
      (await call("GET", "/settings/registration")).data,
    );
    AdminAuthSettingsSchema.parse((await call("GET", "/settings/auth")).data);
    const smtp = (await call("GET", "/settings/smtp")).data;
    AdminSmtpSettingsSchema.parse(smtp);
    expect(JSON.stringify(smtp)).not.toMatch(/secret|"password":/);
    const providers = AdminOidcProviderPageSchema.parse(
      (await call("GET", "/oidc-providers")).data,
    );
    expect(JSON.stringify(providers)).not.toContain('"client_secret"');
  });

  it("не-админу /api/admin отвечает 404", async () => {
    activateServerScenario("student_ready");
    expect((await call("GET", "/settings/registration")).status).toBe(404);
  });

  it("заданное окружением только читается", async () => {
    activateServerScenario("admin_env_locked");
    const user = userEvent.setup();
    mount();
    const form = await screen.findByTestId("registration-form");
    expect(within(form).getByTestId("registration-mode-invite")).toBeVisible();
    for (const radio of within(form).getAllByRole("radio")) {
      expect(radio).toBeDisabled();
    }
    expect(screen.getByTestId("registration-approval")).toBeDisabled();
    expect(screen.getByTestId("registration-mode-locked")).toBeVisible();
    // Домены задал администратор: поле открыто.
    expect(screen.getByLabelText("Разрешённые домены")).not.toHaveAttribute(
      "readonly",
    );
    // Почта целиком от окружения: поля только читаются, замок в каждой строке
    // и внутри поля, плюс пометка внизу раздела.
    const host = screen.getByTestId("smtp-host");
    expect(within(host).getAllByRole("textbox")[0]).toHaveAttribute("readonly");
    expect(within(host).getAllByTestId("input-locked")[0]).toBeVisible();
    expect(screen.getByTestId("smtp-host-locked")).toBeVisible();
    expect(
      within(screen.getByTestId("admin-smtp")).getByTestId("all-locked-note"),
    ).toBeVisible();
    await user.click(screen.getByTestId("registration-mode-open"));
    expect(
      screen.getByTestId("registration-mode-domains").querySelector("input"),
    ).toBeChecked();
  });

  it("секреты не показываются: пароль почты и секрет провайдера", async () => {
    const user = userEvent.setup();
    mount();
    const password = await screen.findByLabelText("Пароль");
    expect(password).toHaveAttribute("type", "password");
    expect(password).toHaveValue("");
    expect(screen.getByTestId("smtp-password-set")).toBeVisible();

    await user.type(password, "very-secret-pass");
    await user.click(screen.getByTestId("save-bar-save"));
    await waitFor(() => {
      expect(screen.queryByTestId("save-bar")).toBeNull();
    });
    expect(screen.getByLabelText("Пароль")).toHaveValue("");
    expect(document.body.textContent).not.toContain("very-secret-pass");

    await openMenu(user, "HSE SSO");
    await user.click(await screen.findByTestId("oidc-edit-keycloak"));
    const secret = await screen.findByLabelText("Секрет клиента");
    expect(secret).toHaveAttribute("type", "password");
    expect(secret).toHaveValue("");
    expect(screen.getByTestId("oidc-secret-set")).toBeVisible();
  });

  it("регистрация по доменам: проверка списка и сохранение", async () => {
    const user = userEvent.setup();
    mount();
    await screen.findByTestId("registration-form");
    await user.click(screen.getByTestId("registration-mode-domains"));
    expect(screen.getByText("Укажите хотя бы один домен.")).toBeInTheDocument();
    const domains = screen.getByLabelText("Разрешённые домены");
    await user.type(domains, "hse,ru");
    expect(screen.getByText(/Это не похоже на домен: hse/)).toBeInTheDocument();
    await user.clear(domains);
    await user.type(domains, "@HSE.ru edu.hse.ru");
    expect(screen.getByTestId("save-bar")).toHaveTextContent(
      "2 несохранённых изменения",
    );
    await user.click(screen.getByTestId("save-bar-save"));
    await waitFor(() => {
      expect(screen.queryByTestId("save-bar")).toBeNull();
    });
    expect(screen.getByLabelText("Разрешённые домены")).toHaveValue(
      "hse.ru, edu.hse.ru",
    );
  });

  it("единственный способ входа нельзя отключить", async () => {
    const user = userEvent.setup();
    mount();
    await screen.findByTestId("signin-form");
    // В admin_ready один включённый провайдер: пароль выключить можно.
    expect(screen.getByTestId("signin-password")).toBeEnabled();
    await openMenu(user, "HSE SSO");
    await user.click(await screen.findByTestId("oidc-toggle-keycloak"));
    await waitFor(() => {
      expect(screen.getByTestId("signin-password")).toBeDisabled();
    });
    expect(screen.getByText(/единственный способ входа/)).toBeInTheDocument();
  });

  it("сервер отказывает убрать последний способ входа", async () => {
    activateServerScenario("admin_sso");
    const user = userEvent.setup();
    mount();
    await openMenu(user, "HSE SSO");
    await user.click(await screen.findByTestId("oidc-toggle-keycloak"));
    await waitFor(() => {
      expect(screen.getByTestId("oidc-state-keycloak")).toHaveTextContent(
        "Выключен",
      );
    });
    await openMenu(user, "Google");
    await user.click(await screen.findByTestId("oidc-toggle-google"));
    expect(
      await screen.findAllByText(/Нельзя убрать последний способ входа/),
    ).not.toHaveLength(0);
  });

  it("форма провайдера: проверка, redirect URI и создание", async () => {
    const user = userEvent.setup();
    mount();
    await user.click(await screen.findByTestId("oidc-add"));
    const dialog = await screen.findByRole("dialog");
    expect(
      within(within(dialog).getByTestId("oidc-redirect")).getByLabelText(
        "Адрес возврата (redirect URI)",
      ),
    ).toHaveValue(`${window.location.origin}/auth/oidc/{id}/callback`);
    await user.type(
      within(dialog).getByLabelText("Название на кнопке"),
      "Test",
    );
    await user.type(
      within(dialog).getByLabelText("Адрес издателя (issuer)"),
      "http://id.example.org",
    );
    await user.type(
      within(dialog).getByLabelText("Идентификатор клиента"),
      "studio",
    );
    await user.click(within(dialog).getByTestId("oidc-form-save"));
    expect(within(dialog).getByText(/Нужен https/)).toBeInTheDocument();
    expect(
      within(dialog).getByText("Укажите секрет клиента."),
    ).toBeInTheDocument();

    const issuer = within(dialog).getByLabelText("Адрес издателя (issuer)");
    await user.clear(issuer);
    await user.type(issuer, "https://sso.example.org");
    await user.type(
      within(dialog).getByLabelText("Секрет клиента"),
      "s3cret-value",
    );
    await user.click(within(dialog).getByTestId("oidc-form-save"));
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).toBeNull();
    });
    expect(await screen.findByText("Test")).toBeVisible();
    expect(document.body.textContent).not.toContain("s3cret-value");
  });

  it("тестовое письмо: успех и отказ", async () => {
    const user = userEvent.setup();
    mount();
    await user.click(await screen.findByTestId("smtp-test-send"));
    expect(await screen.findByTestId("smtp-test-ok")).toHaveTextContent(
      "Письмо отправлено на ivan.sidorov@example.org",
    );
    await user.type(screen.getByLabelText("Кому"), "fail@example.org");
    await user.click(screen.getByTestId("smtp-test-send"));
    expect(await screen.findByTestId("smtp-test-failed")).toHaveTextContent(
      "SMTPConnectError",
    );
  });

  it("правки разных разделов сохраняет одна панель, «Отменить» сбрасывает", async () => {
    const user = userEvent.setup();
    mount();
    await screen.findByTestId("registration-form");
    await user.click(screen.getByTestId("registration-mode-closed"));
    await user.click(screen.getByTestId("signin-password"));
    expect(screen.getByTestId("save-bar")).toHaveTextContent(
      "2 несохранённых изменения",
    );
    // Пока есть правки почты, тест проверил бы старые настройки.
    await user.clear(screen.getByLabelText("Имя отправителя"));
    await user.type(screen.getByLabelText("Имя отправителя"), "Studio ВШЭ");
    expect(screen.getByTestId("smtp-test-send")).toHaveAttribute(
      "aria-disabled",
      "true",
    );
    await user.click(screen.getByTestId("save-bar-discard"));
    expect(screen.queryByTestId("save-bar")).toBeNull();
    expect(
      screen.getByTestId("registration-mode-invite").querySelector("input"),
    ).toBeChecked();
    expect(screen.getByTestId("signin-password")).toBeChecked();
    expect(screen.getByLabelText("Имя отправителя")).toHaveValue("Studio");
  });

  it("без прав страница показывает ошибку с повтором", async () => {
    activateServerScenario("student_ready");
    mount();
    expect(
      await screen.findByTestId("admin-settings-failed"),
    ).toHaveTextContent("Не удалось загрузить настройки");
  });

  it("провайдеры входа: поиск на сервере и «ничего не найдено»", async () => {
    const user = userEvent.setup();
    mount();
    const section = await screen.findByTestId("admin-oidc");
    await within(section).findByTestId("oidc-provider-keycloak");
    await user.type(within(section).getByRole("searchbox"), "нет-такого");
    expect(
      await within(section).findByTestId("oidc-none", {}, { timeout: 5000 }),
    ).toHaveTextContent("Ничего не найдено");
    // «Добавить» остаётся в шапке: пустое состояние без кнопки создания.
    expect(within(section).getByTestId("oidc-add")).toBeVisible();
    await user.click(
      within(within(section).getByTestId("oidc-none")).getByRole("button", {
        name: "Сбросить фильтры",
      }),
    );
    expect(
      await within(section).findByTestId("oidc-provider-keycloak"),
    ).toBeVisible();
  });

  it("провайдеры входа: состояние из адреса отбирает на сервере", async () => {
    mount("/admin/settings?oidc.enabled=false");
    const section = await screen.findByTestId("admin-oidc");
    expect(await within(section).findByTestId("oidc-none")).toBeVisible();
    expect(
      within(section).getByTestId("oidc-filter-enabled"),
    ).toHaveTextContent("Выключен");
    expect(within(section).queryByTestId("oidc-empty")).toBeNull();
  });

  it("почта выключена: тест недоступен", async () => {
    activateServerScenario("admin_sso");
    mount();
    await screen.findByTestId("smtp-test");
    expect(screen.getByTestId("smtp-status")).toHaveTextContent("Выключена");
    expect(screen.getByTestId("smtp-test-send")).toHaveAttribute(
      "aria-disabled",
      "true",
    );
  });
});

describe("проверки форм", () => {
  it("домены нормализуются", () => {
    expect(parseDomains("@HSE.ru, edu.hse.ru hse.ru")).toEqual([
      "hse.ru",
      "edu.hse.ru",
    ]);
  });

  it("издатель OIDC: https, localhost по http, без параметров", () => {
    const base = {
      ...emptyOidcDraft(),
      label: "x",
      client_id: "c",
      client_secret: "s",
    };
    const issue = (issuer: string) =>
      validateOidc({ ...base, issuer }, { creating: true }).issuer;
    expect(issue("https://id.example.org")).toBeUndefined();
    expect(issue("http://localhost:8080")).toBeUndefined();
    expect(issue("http://id.example.org")).toBe("issuerInsecure");
    expect(issue("id.example.org")).toBe("issuerInvalid");
    expect(issue("https://id.example.org?x=1")).toBe("issuerInvalid");
    expect(issue("")).toBe("issuerRequired");
  });
});
