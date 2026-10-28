import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { I18nextProvider } from "react-i18next";
import { afterEach, beforeAll, beforeEach, describe, expect, it } from "vitest";
import { apiClient, setCsrfToken } from "@shared/api";
import { i18n } from "@shared/lib";
import { SetupWizard } from "@features/server-setup";
import { installServerDemo } from "../index";
import { activateServerScenario, enableServerDemo } from "./index";
import { getServerWorld } from "./routes";
import { DEMO_SETUP_TOKEN } from "./scenarios";

// Мастер первого запуска поверх демо-транспорта: те же запросы /server-setup/*,
// что уйдут настоящему бэкенду, и те же ответы, что видит человек в демо.

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
          <SetupWizard signIn={<p data-testid="slot-sign-in">форма входа</p>} />
        </MemoryRouter>
      </QueryClientProvider>
    </I18nextProvider>,
  );

const field = (label: string) =>
  screen.findByLabelText(label, { selector: "input" });

const stepIs = async (step: string) =>
  waitFor(() => {
    expect(screen.getByTestId("setup-wizard")).toHaveAttribute(
      "data-step",
      step,
    );
  });

const createAdmin = async (
  user: ReturnType<typeof userEvent.setup>,
  email = "ivan@example.org",
  token: string | null = DEMO_SETUP_TOKEN,
) => {
  await user.click(await screen.findByTestId("setup-next"));
  if (token !== null) await user.type(await field("Токен установки"), token);
  await user.type(await field("Имя"), "Иван Сидоров");
  await user.type(await field("Почта"), email);
  await user.type(await field("Пароль"), "correct horse battery");
  await user.type(await field("Повторите пароль"), "correct horse battery");
  await user.click(screen.getByTestId("setup-admin-submit"));
};

const signInAsAdmin = async () => {
  const res = await apiClient.post<{ csrf_token: string }>("/auth/login", {
    email: "ivan.sidorov@example.org",
    password: "correct horse battery",
  });
  setCsrfToken(res.data.csrf_token);
};

describe("демо: мастер первого запуска", () => {
  beforeAll(() => {
    installServerDemo();
    enableServerDemo();
  });
  beforeEach(async () => {
    setCsrfToken(null);
    await i18n.changeLanguage("ru");
  });
  afterEach(cleanup);

  it("проходит шаги по порядку до экрана «Готово» и закрывает мастер", async () => {
    activateServerScenario("fresh_install");
    const user = userEvent.setup();
    mount();
    await stepIs("language");

    await createAdmin(user);
    await stepIs("registration");
    expect(screen.getByTestId("setup-mode-invite")).toHaveAttribute(
      "data-active",
      "true",
    );

    await user.click(screen.getByTestId("setup-next"));
    await stepIs("signin");
    await user.click(screen.getByTestId("setup-save"));

    await stepIs("environment");
    expect(await screen.findByTestId("setup-check-database")).toHaveAttribute(
      "data-status",
      "ok",
    );
    expect(
      screen.getByTestId("setup-environment-warnings"),
    ).toBeInTheDocument();

    await user.click(screen.getByTestId("setup-complete"));
    await stepIs("done");
    expect(getServerWorld().bootstrap.setup_state).toBe("ready");
    expect(getServerWorld().setup.settings.registration_mode).toBe("invite");
  });

  it("неверный токен установки остаётся у поля и админ не создаётся", async () => {
    activateServerScenario("fresh_install");
    const user = userEvent.setup();
    mount();
    await createAdmin(user, "ivan@example.org", "st_wrong");
    expect(
      await screen.findByText("Токен установки неверный."),
    ).toBeInTheDocument();
    expect(getServerWorld().setup.adminExists).toBe(false);
    await stepIs("admin");
  });

  it("проигравший гонку видит нейтральный экран, а не ошибку", async () => {
    activateServerScenario("fresh_install");
    const user = userEvent.setup();
    mount();
    await createAdmin(user, "race@example.org");
    expect(await screen.findByTestId("setup-occupied")).toBeInTheDocument();
    expect(screen.getByTestId("slot-sign-in")).toBeInTheDocument();
    expect(screen.queryByTestId("setup-error")).toBeNull();
    expect(screen.queryByTestId("setup-wizard")).toBeNull();
  });

  it("админ уже создан другим: нейтральный экран с формой входа", async () => {
    activateServerScenario("fresh_install_raced");
    mount();
    expect(await screen.findByTestId("setup-occupied")).toHaveAttribute(
      "data-signed-in",
      "false",
    );
    expect(screen.getByTestId("slot-sign-in")).toBeInTheDocument();
  });

  it("админ из окружения: после входа режим регистрации только для чтения", async () => {
    activateServerScenario("fresh_install_env");
    await signInAsAdmin();
    const user = userEvent.setup();
    mount();
    // Режим задан окружением, шаг настроек засчитан: мастер встаёт на окружение.
    await stepIs("environment");
    await user.click(await screen.findByRole("button", { name: "Назад" }));
    await user.click(await screen.findByRole("button", { name: "Назад" }));
    await stepIs("registration");
    for (const radio of screen.getAllByRole("radio")) {
      expect(radio).toBeDisabled();
    }
    expect(screen.getByTestId("setup-mode-domains")).toHaveAttribute(
      "data-active",
      "true",
    );
    expect(await field("Разрешённые домены")).toHaveAttribute("readonly");
    expect(screen.getAllByTestId("locked-by-env").length).toBeGreaterThan(0);
  });

  it("красное хранилище не пускает завершить настройку", async () => {
    activateServerScenario("fresh_install_broken");
    await signInAsAdmin();
    getServerWorld().setup.adminExists = true;
    getServerWorld().setup.settingsDone = true;
    const user = userEvent.setup();
    mount();
    await stepIs("environment");
    expect(
      await screen.findByTestId("setup-environment-blocked"),
    ).toBeInTheDocument();
    await user.click(screen.getByTestId("setup-complete"));
    expect(getServerWorld().setup.completed).toBe(false);
    expect(screen.getByTestId("setup-wizard")).toHaveAttribute(
      "data-step",
      "environment",
    );
  });
});
