import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { settingsApi, type SettingsData } from "@entities/app-settings";
import { gitRemoteApi } from "@entities/git-remote";
import { profileApi, type Profile } from "@entities/profile";
import { i18n } from "@shared/lib/i18n";

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

import { SettingsPage } from "./SettingsPage";

const PROFILE: Profile = {
  name: null,
  email: null,
  effective_name: "HSE Doc Studio",
  effective_email: "studio@hse-doc-studio.local",
  is_default: true,
  commit_preview: "HSE Doc Studio <studio@hse-doc-studio.local>",
};

const mount = (path = "/settings/profile") =>
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/settings/:section" element={<SettingsPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );

describe("SettingsPage: author profile section", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
    vi.spyOn(profileApi, "get").mockResolvedValue(PROFILE);
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("is listed in the General group and opens its form", async () => {
    mount();
    const link = screen.getByRole("link", { name: "Автор версий" });
    expect(link).toHaveAttribute("href", "/settings/profile");
    expect(link).toHaveClass("active");
    expect(await screen.findByLabelText("Имя")).toBeInTheDocument();
    const groups = [...document.querySelectorAll(".settings-modal-group")].map(
      (el) => el.textContent,
    );
    expect(groups[0]).toBe("Общие");
  });

  it("is found by search and the result opens the section", async () => {
    const user = userEvent.setup();
    mount("/settings/appearance");
    await user.type(
      screen.getByPlaceholderText("Поиск по настройкам"),
      "почта",
    );
    const result = await screen.findByRole("button", { name: /E-mail автора/ });
    await user.click(result);
    await waitFor(() => {
      expect(screen.getByLabelText("Имя")).toBeInTheDocument();
    });
  });

  it("is found by an English keyword while the interface is in Russian", async () => {
    const user = userEvent.setup();
    mount("/settings/appearance");
    await user.type(
      screen.getByPlaceholderText("Поиск по настройкам"),
      "commit",
    );
    expect(
      await screen.findByRole("button", { name: /Автор версий/ }),
    ).toBeInTheDocument();
  });
});

describe("SettingsPage: repository access section", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
    // jsdom has no scrollIntoView, which the "jump to setting" flash calls.
    Element.prototype.scrollIntoView = vi.fn();
    vi.spyOn(gitRemoteApi, "listCredentials").mockResolvedValue([]);
    vi.spyOn(gitRemoteApi, "listHosts").mockResolvedValue([]);
    vi.spyOn(gitRemoteApi, "getSecretsStatus").mockResolvedValue({
      ok: true,
      source: "file",
      permissions_enforced: true,
      credentials_total: 0,
      credentials_unreadable: 0,
      data_dir_shared_folder: null,
    });
    vi.spyOn(settingsApi, "get").mockResolvedValue({
      git_fetch_interval_s: 300,
    } as unknown as SettingsData);
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("is listed in the System group and opens its blocks", async () => {
    mount("/settings/git-access");
    const link = screen.getByRole("link", { name: "Доступ к репозиториям" });
    expect(link).toHaveAttribute("href", "/settings/git-access");
    expect(link).toHaveClass("active");
    expect(link.previousElementSibling?.closest("nav")).toBeTruthy();
    const groups = [...document.querySelectorAll(".settings-modal-group")].map(
      (el) => el.textContent,
    );
    expect(groups.at(-1)).toBe("Система");
    expect(await screen.findByText("Доверенные серверы")).toBeInTheDocument();
    expect(await screen.findByText("Шифрование")).toBeInTheDocument();
  });

  it("is found by search in Russian and English and the result opens the section", async () => {
    const user = userEvent.setup();
    mount("/settings/appearance");
    const search = screen.getByPlaceholderText("Поиск по настройкам");
    await user.type(search, "fingerprint");
    const result = await screen.findByRole("button", {
      name: /Доверенные серверы/,
    });
    await user.click(result);
    expect(await screen.findByText("Токены и ключи")).toBeInTheDocument();
    await user.clear(search);
    await user.type(search, "токен");
    expect(
      await screen.findByRole("button", { name: /Токены и ключи/ }),
    ).toBeInTheDocument();
  });
});
