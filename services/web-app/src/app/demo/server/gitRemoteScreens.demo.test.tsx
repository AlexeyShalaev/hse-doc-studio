import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, beforeAll, beforeEach, describe, expect, it } from "vitest";
import { i18n } from "@shared/lib";
import { GitServerSource } from "@features/git-server";
import { DevicePage } from "@pages/DevicePage";
import { SyncServerCloneSection } from "@pages/WorkspacePage/panels/project-settings";
import { resetGitServersDemo } from "../gitServers";
import { installServerDemo } from "../index";
import { activateServerScenario } from "./index";

// Сервер как git-remote на демо-мире (разделы 10.11–10.13): страница /device,
// «Клонировать с сервера» в настройках проекта и источник «Сервер HSE Doc
// Studio» в мастере клонирования. Запросы те же, что уйдут бэкенду.

const wrap = (path: string, element: ReactNode, route = "*") =>
  render(
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
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path={route} element={element} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );

describe("сервер как git-remote на демо-мире", () => {
  beforeAll(() => {
    installServerDemo();
  });
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
    activateServerScenario("student_ready");
    resetGitServersDemo();
  });
  afterEach(cleanup);

  it("/device: разрешение только на чтение даёт итог approved", async () => {
    const user = userEvent.setup();
    wrap("/device?code=bcdf-2345", <DevicePage />, "/device");
    expect(await screen.findByTestId("device-card")).toBeInTheDocument();
    expect(screen.getByTestId("device-user-code")).toHaveTextContent(
      "BCDF-2345",
    );
    await user.click(screen.getByTestId("device-scope-write"));
    await user.click(screen.getByTestId("device-approve"));
    expect(await screen.findByTestId("device-result")).toHaveAttribute(
      "data-state",
      "approved",
    );
  });

  it.each([
    ["XKCD-7777", "expired"],
    ["QRST-2468", "used"],
    ["ZZZZ-2222", "invalid"],
    ["nonsense", "invalid"],
  ])("/device: код %s даёт итог %s", async (code, result) => {
    wrap(`/device?code=${code}`, <DevicePage />, "/device");
    expect(await screen.findByTestId("device-result")).toHaveAttribute(
      "data-state",
      result,
    );
  });

  it("/device: CLI просит только чтение, запись не включить; отказ", async () => {
    const user = userEvent.setup();
    wrap("/device?code=HJKL-3456", <DevicePage />, "/device");
    await screen.findByTestId("device-card");
    expect(screen.getByTestId("device-scope-write")).toBeDisabled();
    await user.click(screen.getByTestId("device-deny"));
    expect(await screen.findByTestId("device-result")).toHaveAttribute(
      "data-state",
      "denied",
    );
  });

  it("/device без кода спрашивает код и переходит к запросу", async () => {
    const user = userEvent.setup();
    wrap("/device", <DevicePage />, "/device");
    await user.type(await screen.findByTestId("device-code-input"), "bcdf2345");
    await user.click(screen.getByTestId("device-code-continue"));
    expect(await screen.findByTestId("device-card")).toBeInTheDocument();
  });

  it("клонировать с сервера: адрес, ветка и право отправки по роли", async () => {
    wrap("/", <SyncServerCloneSection projectId="p_01hxa1c4de" />);
    const block = await screen.findByTestId("project-git-remote");
    await waitFor(() => {
      expect(block).toHaveAttribute("data-state", "ready");
    });
    expect(screen.getByTestId("project-git-remote-url").innerHTML).toContain(
      "https://studio.example.org/git/p_01hxa1c4de.git",
    );
    expect(screen.getByTestId("project-git-remote-push")).toHaveAttribute(
      "data-can-push",
      "true",
    );
    cleanup();
    wrap("/", <SyncServerCloneSection projectId="p_01hxa2f8gh" />);
    await waitFor(() => {
      expect(screen.getByTestId("project-git-remote-push")).toHaveAttribute(
        "data-can-push",
        "false",
      );
    });
  });

  it("клонировать с сервера: вкладка командной строки ведёт к токену для git", async () => {
    const user = userEvent.setup();
    wrap("/", <SyncServerCloneSection projectId="p_01hxa1c4de" />);
    await user.click(await screen.findByTestId("project-git-remote-tab-cli"));
    expect(screen.getByTestId("project-git-remote-token")).toHaveAttribute(
      "href",
      "/settings/account?preset=git#account-tokens",
    );
  });

  it("источник «Сервер Студии»: сервер, проекты и выбор проекта", async () => {
    const user = userEvent.setup();
    const picked: string[] = [];
    wrap(
      "/",
      <GitServerSource
        clientName="Студия"
        onPick={(project, credentialId) => {
          picked.push(`${project.clone_url}|${credentialId}`);
        }}
      />,
    );
    expect(
      await screen.findByTestId("git-server-cred_studio_revoked"),
    ).toHaveAttribute("data-state", "revoked");
    await user.click(screen.getByTestId("git-server-cred_studio_ok"));
    await user.click(
      await screen.findByTestId(
        "git-server-project-clone-6c1d2e3f-4051-4263-9475-8697a8b9c0d1",
      ),
    );
    expect(picked).toEqual([
      "https://studio.example.org/git/6c1d2e3f-4051-4263-9475-8697a8b9c0d1.git|cred_studio_ok",
    ]);
  });

  it("источник «Сервер Студии»: адрес не Студии даёт текст ошибки", async () => {
    const user = userEvent.setup();
    wrap("/", <GitServerSource clientName="Студия" onPick={() => undefined} />);
    await user.click(await screen.findByTestId("git-server-login-open"));
    await user.type(
      screen.getByTestId("git-server-url"),
      "https://other.example.org",
    );
    await user.click(screen.getByTestId("git-server-login-submit"));
    expect(
      await screen.findByText("По этому адресу нет сервера HSE Doc Studio."),
    ).toBeInTheDocument();
  });

  it("источник «Сервер Студии»: вход кодом показывает код и ссылку", async () => {
    const user = userEvent.setup();
    wrap("/", <GitServerSource clientName="Студия" onPick={() => undefined} />);
    await user.click(await screen.findByTestId("git-server-login-open"));
    await user.type(
      screen.getByTestId("git-server-url"),
      "https://new.example.org",
    );
    await user.click(screen.getByTestId("git-server-login-submit"));
    expect(
      await screen.findByTestId("git-server-login-user-code"),
    ).toHaveTextContent("BCDF-2345");
    expect(screen.getByTestId("git-server-login-open-browser")).toHaveAttribute(
      "href",
      "https://new.example.org/device?code=BCDF-2345",
    );
  });
});
