import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  cleanup,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { I18nextProvider } from "react-i18next";
import { afterEach, beforeAll, beforeEach, describe, expect, it } from "vitest";
import { i18n } from "@shared/lib";
import { AccountSection } from "@features/account-settings";
import {
  AccountIdentitySchema,
  AccountProfileSchema,
  AccountSessionSchema,
  ApiTokenSchema,
  CreateApiTokenResponseSchema,
  ChangeEmailResponseSchema,
} from "@entities/session";
import { createDemoRouter } from "@shared/api/demo";
import type { DemoRequest } from "@shared/api/demo";
import { installServerDemo } from "../index";
import { activateServerScenario, enableServerDemo } from "./index";
import { serverDemoRoutes } from "./routes";
import { z } from "zod";

// Раздел «Аккаунт» поверх демо-транспорта: те же запросы, что уйдут настоящему
// бэкенду, и ответы, проходящие те же схемы.

const mount = () =>
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
        <MemoryRouter>
          <AccountSection />
        </MemoryRouter>
      </QueryClientProvider>
    </I18nextProvider>,
  );

const router = createDemoRouter(serverDemoRoutes);
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

describe("демо: раздел «Аккаунт»", () => {
  beforeAll(() => {
    installServerDemo();
    enableServerDemo();
  });
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
    activateServerScenario("student_ready");
  });
  afterEach(cleanup);

  it("ответы демо проходят схемы контракта", async () => {
    expect(
      AccountProfileSchema.parse((await call("GET", "/account")).data).id,
    ).toBe("u_01hx7k2m9c");
    const sessions = z
      .array(AccountSessionSchema)
      .parse((await call("GET", "/account/sessions")).data);
    expect(sessions.filter((s) => s.current)).toHaveLength(1);
    ChangeEmailResponseSchema.parse(
      (await call("POST", "/account/email", { email: "a@b.co", password: "x" }))
        .data,
    );
  });

  it("показывает профиль, подпись по умолчанию и сессии", async () => {
    mount();
    expect(await screen.findByTestId("account-email-value")).toHaveTextContent(
      "anna.petrova@example.org",
    );
    expect(await screen.findByTestId("commit-preview")).toHaveTextContent(
      "noreply.studio.example.org",
    );
    expect(await screen.findByTestId("session-ses_demo_current")).toBeVisible();
    expect(
      within(screen.getByTestId("session-ses_demo_current")).queryByRole(
        "button",
      ),
    ).toBeNull();
  });

  it("смена пароля: неверный текущий пароль и успех", async () => {
    const user = userEvent.setup();
    mount();
    await screen.findByTestId("password-form");
    const fill = async (current: string) => {
      await user.type(screen.getByLabelText("Текущий пароль"), current);
      await user.type(
        screen.getByLabelText("Новый пароль"),
        "brand new pass 42",
      );
      await user.type(
        screen.getByLabelText("Повторите новый пароль"),
        "brand new pass 42",
      );
      await user.click(screen.getByTestId("password-submit"));
    };
    await fill("wrong-password");
    expect(
      (await screen.findAllByText("Неверный пароль."))[0],
    ).toBeInTheDocument();
    await user.clear(screen.getByLabelText("Текущий пароль"));
    await user.clear(screen.getByLabelText("Новый пароль"));
    await user.clear(screen.getByLabelText("Повторите новый пароль"));
    await fill("right-password");
    expect(await screen.findByTestId("password-done")).toBeInTheDocument();
    // «Завершить остальные» было включено: в мире осталась только текущая сессия.
    await waitFor(() => {
      expect(screen.queryByTestId("session-ses_demo_phone")).toBeNull();
    });
    expect(screen.getByTestId("sessions-alone")).toBeInTheDocument();
  });

  it("подпись версий: свой адрес сохраняется и виден в предпросмотре", async () => {
    const user = userEvent.setup();
    mount();
    await user.click(await screen.findByLabelText(/Свой адрес/));
    await user.type(
      screen.getByLabelText("Адрес для версий"),
      "anna@personal.example.com",
    );
    await user.click(screen.getByTestId("commit-save"));
    await waitFor(() => {
      expect(screen.getByText("Сохранено")).toBeInTheDocument();
    });
    expect(screen.getByTestId("commit-preview")).toHaveTextContent(
      "anna@personal.example.com",
    );
    const saved = AccountProfileSchema.parse(
      (await call("GET", "/account")).data,
    );
    expect(saved.effective_commit_email).toBe("anna@personal.example.com");
    expect(saved.commit_email_is_noreply).toBe(false);
  });

  it("завершение одной чужой сессии и всех остальных", async () => {
    const user = userEvent.setup();
    mount();
    const phone = await screen.findByTestId("session-ses_demo_phone");
    await user.click(within(phone).getByRole("button", { name: /Завершить/ }));
    await waitFor(() => {
      expect(screen.queryByTestId("session-ses_demo_phone")).toBeNull();
    });
    await user.click(screen.getByTestId("sessions-end-others"));
    await user.click(screen.getByTestId("sessions-end-others-confirm"));
    expect(await screen.findByTestId("sessions-alone")).toBeInTheDocument();
    expect(screen.getByTestId("session-ses_demo_current")).toBeVisible();
  });

  it("без почты ссылка смены адреса показывается на экране", async () => {
    activateServerScenario("student_nosmtp");
    const user = userEvent.setup();
    mount();
    await user.click(
      await screen.findByRole("button", { name: "Сменить адрес" }),
    );
    await user.type(screen.getByLabelText("Новый адрес"), "anna@hse.ru");
    await user.type(
      screen.getByLabelText("Пароль для подтверждения"),
      "secret",
    );
    await user.click(screen.getByRole("button", { name: "Отправить ссылку" }));
    expect(await screen.findByTestId("link-delivery")).toBeInTheDocument();
  });

  it("вход через SSO: вместо формы пароля пояснение", async () => {
    activateServerScenario("student_sso");
    mount();
    await screen.findByTestId("account-profile");
    await waitFor(() => {
      expect(screen.queryByTestId("password-form")).toBeNull();
    });
    expect(screen.getByText(/единый вход/)).toBeInTheDocument();
  });

  it("токен: создание, значение видно один раз, отзыв", async () => {
    const user = userEvent.setup();
    mount();
    await screen.findByTestId("tokens-list");
    await user.click(screen.getByTestId("token-new"));
    await user.type(screen.getByLabelText("Название"), "Мой скрипт");
    await user.click(screen.getByTestId("token-submit"));

    const created = await screen.findByTestId("token-created");
    const value = within(created).getByDisplayValue(/^hsd_pat_/);
    const secret = (value as HTMLInputElement).value;
    // Сервер вернул значение один раз; в списке остаётся только начало.
    const listed = z
      .array(ApiTokenSchema)
      .parse((await call("GET", "/account/tokens")).data);
    expect(JSON.stringify(listed)).not.toContain(secret);
    const row = listed.find((t) => t.name === "Мой скрипт");
    expect(row?.prefix).toBe(secret.slice(0, 11));

    // Закрыть без копирования нельзя сразу: просим подтвердить.
    await user.click(within(created).getByRole("button", { name: "Готово" }));
    await user.click(
      await screen.findByRole("button", { name: "Закрыть без копирования" }),
    );
    await waitFor(() => {
      expect(screen.queryByTestId("token-created")).toBeNull();
    });
    expect(screen.queryByDisplayValue(secret)).toBeNull();
    expect(screen.queryByText(secret)).toBeNull();

    await user.click(screen.getByTestId(`token-revoke-${row?.id ?? ""}`));
    await user.click(
      screen.getByTestId(`token-revoke-confirm-${row?.id ?? ""}`),
    );
    await waitFor(() => {
      expect(screen.queryByTestId(`token-${row?.id ?? ""}`)).toBeNull();
    });
  });

  it("токен: без названия и без прав форма не уходит", async () => {
    const user = userEvent.setup();
    mount();
    await screen.findByTestId("tokens-list");
    await user.click(screen.getByTestId("token-new"));
    await user.click(screen.getByTestId("token-scope-api"));
    await user.click(screen.getByTestId("token-submit"));
    expect(screen.getByText("Укажите название.")).toBeInTheDocument();
    expect(
      screen.getByText("Выберите хотя бы одно право."),
    ).toBeInTheDocument();
    expect(screen.queryByTestId("token-created")).toBeNull();
  });

  it("токен: просроченный помечен, отказ сервера виден в форме", async () => {
    const user = userEvent.setup();
    mount();
    const old = await screen.findByTestId("token-pat_01hx8z");
    expect(within(old).getByText("Истёк")).toBeInTheDocument();
    await user.click(screen.getByTestId("token-new"));
    await user.type(screen.getByLabelText("Название"), "limit-test");
    await user.click(screen.getByTestId("token-submit"));
    expect(
      await screen.findByText(/Слишком много попыток/),
    ).toBeInTheDocument();
    expect(screen.queryByTestId("token-created")).toBeNull();
  });

  it("способы входа: без провайдеров карточки нет", async () => {
    mount();
    await screen.findByTestId("tokens-list");
    expect(screen.queryByTestId("account-identities")).toBeNull();
  });

  it("способы входа: привязка и отвязка, последний способ защищён", async () => {
    activateServerScenario("student_linked");
    const user = userEvent.setup();
    mount();
    const list = await screen.findByTestId("identities-list");
    expect(within(list).getAllByRole("listitem")).toHaveLength(2);
    // Пароль не отвязывается отсюда, SSO отвязывается, пока есть пароль.
    expect(screen.queryByTestId("identity-unlink-idn_password")).toBeNull();

    await user.click(screen.getByTestId("identity-link-google"));
    await waitFor(() => {
      expect(screen.getByTestId("identity-idn_google")).toBeInTheDocument();
    });
    expect(screen.queryByTestId("identity-link-google")).toBeNull();

    await user.click(screen.getByTestId("identity-unlink-idn_google"));
    await user.click(screen.getByTestId("identity-unlink-confirm-idn_google"));
    await waitFor(() => {
      expect(screen.queryByTestId("identity-idn_google")).toBeNull();
    });
    await user.click(screen.getByTestId("identity-unlink-idn_keycloak"));
    await user.click(
      screen.getByTestId("identity-unlink-confirm-idn_keycloak"),
    );
    await waitFor(() => {
      expect(screen.queryByTestId("identity-idn_keycloak")).toBeNull();
    });
    // Остался один пароль: единственный способ, отвязывать больше нечего.
    expect(screen.getByTestId("identities-sole")).toBeInTheDocument();
    const left = z
      .array(AccountIdentitySchema)
      .parse((await call("GET", "/account/identities")).data);
    expect(left).toEqual([]);
  });

  it("способы входа: единственный SSO без пароля не отвязывается", async () => {
    activateServerScenario("student_sso");
    mount();
    const row = await screen.findByTestId("identity-idn_keycloak");
    expect(within(row).queryByRole("button", { name: /Отвязать/ })).toBeNull();
    expect(screen.getByTestId("identity-locked-idn_keycloak")).toBeVisible();
    // Сервер тоже не даст, даже если запрос отправить в обход интерфейса.
    const refused = await call("DELETE", "/account/identities/keycloak");
    expect(refused.status).toBe(409);
    expect((refused.data as { code: string }).code).toBe("last_login_method");
  });

  it("ответы токенов проходят схемы контракта", async () => {
    const made = await call("POST", "/account/tokens", {
      name: "x",
      scopes: ["api"],
      expires_in_days: null,
    });
    expect(made.status).toBe(201);
    CreateApiTokenResponseSchema.parse(made.data);
  });
});
