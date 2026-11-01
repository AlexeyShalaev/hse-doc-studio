import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { MemoryRouter } from "react-router";
import { I18nextProvider } from "react-i18next";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { i18n } from "@shared/lib";
import {
  EnvironmentStep,
  OccupiedCard,
  RegistrationStep,
  SETUP_ERROR_CODES,
  SetupShell,
  getServerSetupGallery,
  setupErrorKey,
} from "./index";

const wrap = (node: React.ReactNode) => (
  <I18nextProvider i18n={i18n}>
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>{node}</MemoryRouter>
    </QueryClientProvider>
  </I18nextProvider>
);

const DRAFT = {
  registration_mode: "domains" as const,
  domains: "hse.ru",
  require_approval: true,
  password_enabled: true,
};

describe("server-setup", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
  });
  afterEach(cleanup);

  it("степпер показывает шесть шагов по порядку и отмечает текущий", () => {
    render(
      wrap(
        <SetupShell step="registration">
          <p>body</p>
        </SetupShell>,
      ),
    );
    const items = screen.getAllByRole("listitem");
    expect(
      items.map((li) =>
        li.textContent.replace(/^\d/, "").split("—")[0]?.trim(),
      ),
    ).toEqual(["Язык", "Админ", "Регистрация", "Входы", "Окружение", "Готово"]);
    expect(items.map((li) => li.getAttribute("data-state"))).toEqual([
      "done",
      "done",
      "current",
      "upcoming",
      "upcoming",
      "upcoming",
    ]);
  });

  it("locked_by_env: заданные окружением поля только для чтения, остальные правятся", () => {
    const onChange = vi.fn();
    render(
      wrap(
        <RegistrationStep
          draft={DRAFT}
          locked={["registration_mode", "registration_domains"]}
          onChange={onChange}
          onBack={() => undefined}
          onNext={() => undefined}
        />,
      ),
    );
    for (const radio of screen.getAllByRole("radio")) {
      expect(radio).toBeDisabled();
    }
    expect(screen.getByLabelText("Разрешённые домены")).toHaveAttribute(
      "readonly",
    );
    expect(screen.getAllByTestId("locked-by-env").length).toBe(2);
    const approval = screen.getByRole("checkbox");
    expect(approval).toBeEnabled();
    fireEvent.click(approval);
    expect(onChange).toHaveBeenCalledWith({ require_approval: false });
  });

  it("без locked_by_env режим выбирается", () => {
    const onChange = vi.fn();
    render(
      wrap(
        <RegistrationStep
          draft={{ ...DRAFT, registration_mode: "invite" }}
          locked={[]}
          onChange={onChange}
          onBack={() => undefined}
          onNext={() => undefined}
        />,
      ),
    );
    expect(screen.getByTestId("setup-mode-invite")).toHaveAttribute(
      "data-active",
      "true",
    );
    fireEvent.click(screen.getByTestId("setup-mode-open"));
    expect(onChange).toHaveBeenCalledWith({ registration_mode: "open" });
    expect(screen.queryByTestId("locked-by-env")).toBeNull();
  });

  it("красная обязательная проверка блокирует завершение", () => {
    const onComplete = vi.fn();
    render(
      wrap(
        <EnvironmentStep
          checks={[
            { id: "database", status: "ok", reason: null },
            { id: "storage", status: "fail", reason: "ClientConnectorError" },
            { id: "runner", status: "not_configured", reason: null },
          ]}
          loading={false}
          onRecheck={() => undefined}
          onBack={() => undefined}
          onComplete={onComplete}
        />,
      ),
    );
    expect(screen.getByTestId("setup-step-environment")).toHaveAttribute(
      "data-blocked",
      "true",
    );
    expect(screen.getByTestId("setup-environment-blocked")).toBeInTheDocument();
    expect(screen.getByText("ClientConnectorError")).toBeInTheDocument();
    const complete = screen.getByTestId("setup-complete");
    expect(complete).toHaveAttribute("aria-disabled", "true");
    fireEvent.click(complete);
    expect(onComplete).not.toHaveBeenCalled();
  });

  it("предупреждение о раннерах не мешает завершить", () => {
    const onComplete = vi.fn();
    render(
      wrap(
        <EnvironmentStep
          checks={[
            { id: "database", status: "ok", reason: null },
            { id: "storage", status: "ok", reason: null },
            { id: "runner", status: "not_configured", reason: null },
          ]}
          loading={false}
          onRecheck={() => undefined}
          onBack={() => undefined}
          onComplete={onComplete}
        />,
      ),
    );
    expect(
      screen.getByTestId("setup-environment-warnings"),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("setup-complete"));
    expect(onComplete).toHaveBeenCalledTimes(1);
  });

  it("нейтральный экран ничего не раскрывает о том, кто настраивает", () => {
    render(wrap(<OccupiedCard signIn={<p>форма входа</p>} />));
    expect(screen.getByTestId("setup-occupied")).toBeInTheDocument();
    expect(screen.getByText("форма входа")).toBeInTheDocument();
    cleanup();
    render(wrap(<OccupiedCard signedIn signIn={<p>форма входа</p>} />));
    expect(screen.queryByText("форма входа")).toBeNull();
  });

  it("у каждого кода отказа есть текст на двух языках и он есть в каталоге", async () => {
    const catalog = JSON.parse(
      readFileSync(
        join(
          import.meta.dirname,
          "../../../../../contracts/server/error_codes.json",
        ),
        "utf8",
      ),
    ) as string[];
    for (const code of SETUP_ERROR_CODES.filter((c) => c !== "network")) {
      expect(catalog, code).toContain(code);
    }
    for (const lng of ["ru", "en"]) {
      await i18n.changeLanguage(lng);
      for (const code of [...SETUP_ERROR_CODES, "unknown"]) {
        expect(i18n.exists(`auth:${setupErrorKey(code)}`), code).toBe(true);
      }
    }
  });

  it("все записи галереи рисуются на обоих языках", async () => {
    const entries = getServerSetupGallery().flatMap((g) => g.entries);
    expect(entries.length).toBeGreaterThan(25);
    for (const lng of ["ru", "en"]) {
      await i18n.changeLanguage(lng);
      for (const entry of entries) {
        const { container, unmount } = render(wrap(entry.render()));
        expect(container.textContent, entry.id).not.toBe("");
        expect(container.textContent, entry.id).not.toMatch(
          /setup\.\w+\.\w|auth:/,
        );
        unmount();
      }
    }
  });
});
