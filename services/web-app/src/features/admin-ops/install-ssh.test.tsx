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
import { installServerDemo } from "@/app/demo";
import { activateServerScenario } from "@/app/demo/server";
import { ensureAdminOpsLocales } from "./lib/locales";
import { RunnersPage } from "./index";

// Мастер установки по SSH поверх демо-транспорта: форма, отпечаток, план, ход, сохранённые доступы.

const wrap = (node: React.ReactNode) => (
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
  </I18nextProvider>
);

const open = async (user: ReturnType<typeof userEvent.setup>) => {
  render(wrap(<RunnersPage />));
  await user.click(await screen.findByTestId("runner-install-open"));
  await user.click(await screen.findByTestId("install-ssh-open"));
  return screen.findByTestId("ssh-form");
};

const fill = async (
  user: ReturnType<typeof userEvent.setup>,
  host: string,
  password = "s3cret",
) => {
  await user.type(screen.getByTestId("ssh-host"), host);
  await user.type(screen.getByTestId("ssh-username"), "deploy");
  await user.type(screen.getByTestId("ssh-password"), password);
};

describe("установка раннера по SSH", () => {
  beforeAll(() => {
    installServerDemo();
  });
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
    await ensureAdminOpsLocales();
    activateServerScenario("admin_ready");
  });
  afterEach(cleanup);

  it("форма не отправляется без адреса, логина и пароля", async () => {
    const user = userEvent.setup();
    await open(user);

    expect(screen.getByTestId("ssh-probe-submit")).toBeDisabled();
    await fill(user, "srv.example.org");
    expect(screen.getByTestId("ssh-probe-submit")).toBeEnabled();
  }, 20_000);

  it("пароль скрыт, ключ вводится в отдельном поле и поля secret не автозаполняются", async () => {
    const user = userEvent.setup();
    await open(user);

    expect(screen.getByTestId("ssh-password")).toHaveAttribute(
      "type",
      "password",
    );
    await user.click(screen.getByTestId("ssh-auth-key"));
    expect(screen.queryByTestId("ssh-password")).toBeNull();
    expect(screen.getByTestId("ssh-private-key")).toBeVisible();
    expect(screen.getByTestId("ssh-passphrase")).toHaveAttribute(
      "type",
      "password",
    );
  }, 20_000);

  it("отпечаток показывается до входа и без подтверждения дальше пути нет", async () => {
    const user = userEvent.setup();
    await open(user);
    await fill(user, "srv.example.org");
    await user.click(screen.getByTestId("ssh-probe-submit"));

    expect(await screen.findByTestId("ssh-fingerprint")).toHaveTextContent(
      /^SHA256:/,
    );
    expect(screen.getByTestId("ssh-key-type")).toHaveTextContent("ssh-ed25519");
    expect(screen.queryByTestId("ssh-install")).toBeNull();
    // Пароль после отправки из формы стёрт.
    expect(screen.queryByTestId("ssh-password")).toBeNull();
  }, 20_000);

  it("весь путь: подтверждение, план, установка по шагам, успех", async () => {
    const user = userEvent.setup();
    await open(user);
    await fill(user, "srv.example.org");
    await user.click(screen.getByTestId("ssh-probe-submit"));
    await user.click(await screen.findByTestId("ssh-confirm"));

    const plan = await screen.findByTestId("ssh-plan");
    expect(within(plan).getByTestId("ssh-plan-docker")).toHaveAttribute(
      "data-action",
      "skip",
    );
    await user.click(screen.getByTestId("ssh-install"));

    expect(
      await screen.findByTestId("install-success", {}, { timeout: 12_000 }),
    ).toBeVisible();
    expect(
      within(screen.getByTestId("install-steps"))
        .getAllByRole("listitem")
        .every((item) => item.getAttribute("data-state") === "done"),
    ).toBe(true);
  }, 30_000);

  it("закрытый защитой адрес объясняется понятно", async () => {
    const user = userEvent.setup();
    await open(user);
    await fill(user, "10.0.0.5");
    await user.click(screen.getByTestId("ssh-probe-submit"));

    const error = await screen.findByTestId("ssh-error");
    expect(error).toHaveTextContent("защитой от обращений во внутреннюю сеть");
    expect(error).toHaveTextContent("SSH_ALLOWLIST");
    expect(screen.queryByTestId("ssh-fingerprint")).toBeNull();
  }, 20_000);

  it("неверный пароль: понятная ошибка, пароль нигде не показан", async () => {
    const user = userEvent.setup();
    await open(user);
    await fill(user, "srv.example.org", "wrong");
    await user.click(screen.getByTestId("ssh-probe-submit"));
    await user.click(await screen.findByTestId("ssh-confirm"));

    const error = await screen.findByTestId("ssh-error");
    expect(error).toHaveTextContent("не принял логин, пароль или ключ");
    expect(document.body.textContent).not.toContain("wrong");
  }, 20_000);

  it("нет Docker: без явного выбора установка не начинается", async () => {
    const user = userEvent.setup();
    await open(user);
    await fill(user, "nodocker.example.org");
    await user.click(screen.getByTestId("ssh-probe-submit"));
    await user.click(await screen.findByTestId("ssh-confirm"));

    await screen.findByTestId("ssh-plan");
    expect(screen.getByTestId("ssh-install")).toBeDisabled();
    await user.click(screen.getByTestId("ssh-install-docker"));
    expect(screen.getByTestId("ssh-install")).toBeEnabled();
  }, 20_000);

  it("сохранение зашифрованно: галочка с пояснением, затем доступ виден фактом наличия и удаляется", async () => {
    const user = userEvent.setup();
    await open(user);
    expect(screen.getByTestId("ssh-form")).toHaveTextContent(
      "нигде не записываются",
    );
    await fill(user, "srv.example.org");
    await user.click(screen.getByTestId("ssh-save"));
    expect(screen.getByTestId("ssh-form")).toHaveTextContent(
      "Их нельзя будет посмотреть, только удалить",
    );
    await user.click(screen.getByTestId("ssh-probe-submit"));
    await user.click(await screen.findByTestId("ssh-confirm"));
    await user.click(await screen.findByTestId("ssh-install"));
    await screen.findByTestId("install-success", {}, { timeout: 12_000 });
    await user.click(screen.getByTestId("install-done"));

    await user.click(await screen.findByTestId("runner-install-open"));
    await user.click(await screen.findByTestId("install-ssh-open"));
    const saved = await screen.findByTestId("ssh-saved");
    expect(saved).toHaveTextContent("deploy@srv.example.org:22");
    expect(saved).toHaveTextContent("Доступ сохранён зашифрованно");
    expect(saved.textContent).not.toContain("s3cret");

    const row = within(saved).getAllByRole("listitem")[0];
    if (!row) throw new Error("нет строки сохранённого доступа");
    await user.click(
      within(row).getByRole("button", { name: "Удалить доступ" }),
    );
    await user.click(
      within(row).getByRole("button", { name: "Точно удалить" }),
    );
    await waitFor(() => {
      expect(screen.queryByTestId("ssh-saved")).toBeNull();
    });
  }, 40_000);

  it("обновление в один клик по сохранённому доступу идёт без ввода пароля", async () => {
    const user = userEvent.setup();
    await open(user);
    await fill(user, "srv.example.org");
    await user.click(screen.getByTestId("ssh-save"));
    await user.click(screen.getByTestId("ssh-probe-submit"));
    await user.click(await screen.findByTestId("ssh-confirm"));
    await user.click(await screen.findByTestId("ssh-install"));
    await screen.findByTestId("install-success", {}, { timeout: 12_000 });
    await user.click(screen.getByTestId("install-done"));

    await user.click(await screen.findByTestId("runner-install-open"));
    await user.click(await screen.findByTestId("install-ssh-open"));
    const saved = await screen.findByTestId("ssh-saved");
    const update = within(saved).getByRole("button", { name: "Обновить" });
    await user.click(update);

    expect(
      await screen.findByTestId("install-success", {}, { timeout: 12_000 }),
    ).toBeVisible();
  }, 60_000);
});
