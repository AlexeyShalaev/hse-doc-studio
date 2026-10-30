import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "@shared/api";
import { i18n } from "@shared/lib/i18n";
import {
  LOCAL_BOOTSTRAP,
  sessionKeys,
  type Bootstrap,
} from "@entities/session";

vi.mock("@widgets/AppTitlebar", () => ({ AppTitlebar: () => null }));
vi.mock("@widgets/AppStatusBar", () => ({ AppStatusBar: () => null }));
vi.mock("@widgets/settings", async () => {
  const actual =
    await vi.importActual<Record<string, unknown>>("@widgets/settings");
  const Stub = () => null;
  return {
    ...actual,
    AboutSection: Stub,
    AgentPersonasSection: Stub,
    AppearanceSection: Stub,
    ChecksSection: Stub,
    CompilerSection: Stub,
    DiskUsageSection: Stub,
    FontsSection: Stub,
    ImagesSection: Stub,
    LocalModelsSection: Stub,
    OfficeServicesSection: Stub,
    ProvidersSection: Stub,
    SigningIdentitiesSection: Stub,
  };
});
vi.mock("@features/export-import", () => ({ ExportImportSection: () => null }));
vi.mock("@features/account-settings", () => ({
  AccountSection: () => <div data-testid="account-section" />,
}));
vi.mock("@features/author-profile", () => ({
  AuthorProfileSection: () => null,
}));
vi.mock("@features/git-remote", () => ({ GitAccessSection: () => null }));

import { SettingsPage } from "./SettingsPage";

const SERVER: Bootstrap = {
  ...LOCAL_BOOTSTRAP,
  mode: "server",
  capabilities: {
    fs_browse: false,
    connect_folder: false,
    open_in_editor: false,
    move_project: false,
    docker_ui: false,
    self_update: false,
    local_services_ui: false,
    admin: false,
    personal_signing_keys: true,
  },
};

const HIDDEN_HREFS = [
  "/settings/compiler",
  "/settings/fonts",
  "/settings/presentations",
  "/settings/disk",
  "/settings/local-models",
  "/settings/data",
];

const Where = () => <span data-testid="where">{useLocation().pathname}</span>;

const mount = (path: string, bootstrap: Bootstrap | null) => {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  });
  if (bootstrap) client.setQueryData(sessionKeys.bootstrap(), bootstrap);
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Where />
        <Routes>
          <Route path="/settings/:section" element={<SettingsPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
};

const navHrefs = () =>
  within(document.querySelector<HTMLElement>(".settings-modal-nav")!)
    .getAllByRole("link")
    .map((a) => a.getAttribute("href"));

describe("SettingsPage: sections by capabilities", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("local: every section is listed", () => {
    mount("/settings/appearance", LOCAL_BOOTSTRAP);
    const hrefs = navHrefs();
    for (const href of HIDDEN_HREFS) expect(hrefs).toContain(href);
    expect(hrefs).toHaveLength(14);
  });

  it("server: Docker, images, fonts, disk, local models and data export are hidden", () => {
    mount("/settings/appearance", SERVER);
    const hrefs = navHrefs();
    for (const href of HIDDEN_HREFS) expect(hrefs).not.toContain(href);
    expect(hrefs).toEqual(
      expect.arrayContaining([
        "/settings/appearance",
        "/settings/profile",
        "/settings/checks",
        "/settings/signing",
        "/settings/providers",
        "/settings/agent-personas",
        "/settings/about",
      ]),
    );
  });

  it("server с вошедшим человеком: «Аккаунт» вместо второго профиля автора", () => {
    mount("/settings/account", {
      ...SERVER,
      user: {
        id: "u_1",
        name: "Анна Петрова",
        email: "anna@example.org",
        avatar_initials: "АП",
        is_instance_admin: false,
        email_verified: true,
        locale: "ru",
        org_roles: [],
      },
    });
    const hrefs = navHrefs();
    expect(hrefs).toContain("/settings/account");
    expect(hrefs).not.toContain("/settings/profile");
    expect(screen.getByTestId("account-section")).toBeInTheDocument();
  });

  it("server без пользователя и local: раздела «Аккаунт» нет, автор версий на месте", () => {
    mount("/settings/appearance", SERVER);
    expect(navHrefs()).not.toContain("/settings/account");
    expect(navHrefs()).toContain("/settings/profile");
  });

  it("server: search does not find hidden settings", async () => {
    const user = userEvent.setup();
    mount("/settings/appearance", SERVER);
    const search = screen.getByPlaceholderText("Поиск по настройкам");
    await user.type(search, "шрифт");
    expect(screen.getByText("Ничего не найдено")).toBeInTheDocument();
  });

  it("local: the same search finds the Docker settings", async () => {
    const user = userEvent.setup();
    mount("/settings/appearance", LOCAL_BOOTSTRAP);
    await user.type(
      screen.getByPlaceholderText("Поиск по настройкам"),
      "docker",
    );
    expect(
      document.querySelectorAll(".settings-modal-result").length,
    ).toBeGreaterThan(0);
  });

  it("server: a direct link to a hidden section lands on the first available one", () => {
    mount("/settings/compiler", SERVER);
    expect(screen.getByTestId("where")).toHaveTextContent(
      "/settings/appearance",
    );
  });

  it("server: opening settings sends no local requests", () => {
    const get = vi.spyOn(apiClient, "get");
    mount("/settings/appearance", SERVER);
    expect(get).not.toHaveBeenCalled();
  });
});
