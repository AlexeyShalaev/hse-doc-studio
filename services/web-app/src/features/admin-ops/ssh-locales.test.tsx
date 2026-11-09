import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { I18nextProvider } from "react-i18next";
import { MemoryRouter } from "react-router";
import { afterEach, beforeAll, describe, expect, it } from "vitest";
import { i18n } from "@shared/lib";
import { installServerDemo } from "@/app/demo";
import { activateServerScenario } from "@/app/demo/server";
import { SshInstallDialog } from "./index";

// Окно установки по SSH само подключает свои словари: чанк runnerSsh не входит в
// словари страницы раннеров, а страница серверов моделей не грузит и ops с runnerInstall.

const noop = () => undefined;

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

describe("словари окна установки по SSH", () => {
  beforeAll(async () => {
    installServerDemo();
    activateServerScenario("admin_ready");
    await i18n.changeLanguage("ru");
  });
  afterEach(cleanup);

  it("закрытое окно ничего не грузит", () => {
    render(wrap(<SshInstallDialog isOpen={false} onClose={noop} />));
    expect(i18n.hasResourceBundle("ru", "adminRunnerSsh")).toBe(false);
  });

  it("при открытии подгружает runnerSsh, runnerInstall и ops и показывает тексты", async () => {
    expect(i18n.hasResourceBundle("ru", "adminRunnerInstall")).toBe(false);
    render(wrap(<SshInstallDialog isOpen onClose={noop} />));

    await screen.findByTestId("ssh-form");
    expect(screen.getByText("Установка раннера по SSH")).toBeInTheDocument();
    expect(screen.getByLabelText("Адрес хоста")).toBeInTheDocument();
    for (const ns of ["adminRunnerSsh", "adminRunnerInstall", "adminOps"]) {
      expect(i18n.hasResourceBundle("ru", ns)).toBe(true);
      expect(i18n.hasResourceBundle("en", ns)).toBe(true);
    }
  }, 20_000);
});
