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
  AccountProfileSchema,
  AccountSessionSchema,
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
});
