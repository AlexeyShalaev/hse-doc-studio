import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { I18nextProvider } from "react-i18next";
import { afterEach, beforeAll, beforeEach, describe, expect, it } from "vitest";
import { i18n } from "@shared/lib";
import { ForgotForm, ResetForm, VerifyEmail } from "@features/account-recovery";
import { InviteForm, SignUpForm } from "@features/sign-up";
import { installServerDemo } from "../index";
import { activateServerScenario, enableServerDemo } from "./index";

// Экраны регистрации и ссылок из писем поверх демо-транспорта: те же запросы,
// что уйдут настоящему бэкенду, и те же ответы, что видит человек в демо.

const mount = (node: React.ReactNode) =>
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
        <MemoryRouter>{node}</MemoryRouter>
      </QueryClientProvider>
    </I18nextProvider>,
  );

const input = (label: string) =>
  screen.findByLabelText(label, { selector: "input" });

const fillRegistration = async (
  user: ReturnType<typeof userEvent.setup>,
  email: string,
) => {
  await user.type(await input("Имя"), "Maria Keller");
  await user.type(await input("Почта"), email);
  await user.type(await input("Пароль"), "correct horse battery");
  await user.type(await input("Повторите пароль"), "correct horse battery");
  await user.click(screen.getByRole("button", { name: "Создать аккаунт" }));
};

describe("демо: регистрация и ссылки из писем", () => {
  beforeAll(() => {
    installServerDemo();
    enableServerDemo();
  });
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
  });
  afterEach(cleanup);

  it("открытая регистрация без SMTP показывает ссылку подтверждения", async () => {
    activateServerScenario("registration_open_nosmtp");
    const user = userEvent.setup();
    mount(<SignUpForm />);
    await fillRegistration(user, "maria@example.org");
    expect(await screen.findByTestId("link-delivery")).toBeInTheDocument();
    expect(screen.getByTestId("register-result")).toHaveAttribute(
      "data-tone",
      "ok",
    );
  });

  it("со SMTP итог нейтральный и без ссылки", async () => {
    activateServerScenario("registration_open");
    const user = userEvent.setup();
    mount(<SignUpForm />);
    await fillRegistration(user, "maria@example.org");
    expect(await screen.findByTestId("register-result")).toHaveTextContent(
      "Если адрес maria@example.org подходит",
    );
    expect(screen.queryByTestId("link-delivery")).toBeNull();
  });

  it("режим доменов: чужой домен получает отказ у поля почты", async () => {
    activateServerScenario("registration_domains");
    const user = userEvent.setup();
    mount(<SignUpForm />);
    await fillRegistration(user, "maria@gmail.com");
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("разрешённых доменов");
    expect((await input("Почта")).closest(".field")).toContainElement(alert);
  });

  it("ждёт одобрения: адрес approval@", async () => {
    activateServerScenario("registration_domains");
    const user = userEvent.setup();
    mount(<SignUpForm />);
    await fillRegistration(user, "approval@example.org");
    expect(await screen.findByTestId("register-result")).toHaveAttribute(
      "data-tone",
      "warn",
    );
  });

  it("по приглашению без ссылки формы нет", async () => {
    activateServerScenario("admin_ready");
    mount(<SignUpForm />);
    expect(await screen.findByTestId("register-unavailable")).toHaveAttribute(
      "aria-label",
      "Регистрация по приглашению",
    );
  });

  it("приглашение подставляет почту, просроченное отказывает", async () => {
    activateServerScenario("admin_ready");
    const first = mount(<InviteForm token="inv_demo" />);
    expect(await input("Почта")).toHaveValue("maria.keller@example.org");
    first.unmount();
    mount(<InviteForm token="inv_expired" />);
    expect(await screen.findByTestId("register-unavailable")).toHaveAttribute(
      "aria-label",
      "Приглашение недействительно",
    );
  });

  it("forgot: одинаковый итог, а без SMTP ещё и ссылка", async () => {
    activateServerScenario("registration_open_nosmtp");
    const user = userEvent.setup();
    mount(<ForgotForm />);
    await user.type(await input("Почта"), "nobody@example.org");
    await user.click(screen.getByRole("button", { name: "Отправить ссылку" }));
    expect(await screen.findByTestId("forgot-sent")).toBeInTheDocument();
    expect(screen.getByTestId("link-delivery")).toHaveAttribute(
      "data-kind",
      "reset",
    );
  });

  it("reset: просроченный токен ведёт к новому запросу, действующий меняет пароль", async () => {
    activateServerScenario("registration_open");
    const user = userEvent.setup();
    const expired = mount(<ResetForm token="rs_expired" />);
    await user.type(await input("Новый пароль"), "a much longer passphrase");
    await user.type(
      await input("Повторите пароль"),
      "a much longer passphrase",
    );
    await user.click(screen.getByRole("button", { name: "Сохранить пароль" }));
    expect(await screen.findByTestId("reset-expired")).toBeInTheDocument();
    expired.unmount();

    mount(<ResetForm token="rs_ok" />);
    await user.type(await input("Новый пароль"), "a much longer passphrase");
    await user.type(
      await input("Повторите пароль"),
      "a much longer passphrase",
    );
    await user.click(screen.getByRole("button", { name: "Сохранить пароль" }));
    expect(await screen.findByTestId("reset-done")).toBeInTheDocument();
  });

  it("verify: рабочая ссылка подтверждает почту", async () => {
    activateServerScenario("registration_open");
    mount(<VerifyEmail token="vf_ok" />);
    expect(await screen.findByTestId("verify-done")).toBeInTheDocument();
  });

  it("verify: просроченная ссылка и повторная отправка со ссылкой без SMTP", async () => {
    activateServerScenario("registration_open_nosmtp");
    const user = userEvent.setup();
    mount(<VerifyEmail token="vf_expired" />);
    await waitFor(() => {
      expect(screen.getByTestId("verify-invalid")).toBeInTheDocument();
    });
    await user.type(await input("Почта"), "anna@example.org");
    await user.click(
      screen.getByRole("button", { name: "Отправить ссылку ещё раз" }),
    );
    expect(await screen.findByTestId("verify-resent")).toBeInTheDocument();
    expect(screen.getByTestId("link-delivery")).toHaveAttribute(
      "data-kind",
      "verify",
    );
  });
});
