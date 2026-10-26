import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { settingsApi, type SettingsData } from "@entities/app-settings";
import { gitRemoteApi } from "@entities/git-remote";
import {
  NO_REMOTE_STATUS,
  gitSyncKeys,
  toStatusView,
  type GitStatus,
  type SyncStatusView,
} from "@entities/git-sync";
import { i18n } from "@shared/lib/i18n";
import {
  SyncCiSection,
  SyncExchangeSection,
  SyncOptionsSection,
  SyncRemoteSection,
  SyncSharedFolderSection,
} from "./index";

const PROJECT_ID = "p1";

const status = (overrides: Partial<GitStatus> = {}): SyncStatusView =>
  toStatusView({
    ...NO_REMOTE_STATUS,
    connected: true,
    ui_state: "up_to_date",
    relation: "in_sync",
    remote: {
      display_url: "https://github.com/hse-team/paper",
      kind: "https",
      host: "github.com",
      provider: "github",
      web_url: "https://github.com/hse-team/paper",
      branch: "main",
      local_branch: "main",
      credential: null,
      insecure_http: false,
    },
    auto_fetch: { enabled: true, interval_s: 300, next_fetch_at: null },
    shared_folder: {
      provider: "dropbox",
      root: "/Users/ivan/Dropbox",
      acknowledged: false,
    },
    ...overrides,
  });

const mount = (value: SyncStatusView, ui: React.ReactNode) => {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: Infinity } },
  });
  client.setQueryData(gitSyncKeys.status(PROJECT_ID), value);
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
};

describe("карточки группы «Синхронизация»", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
    vi.spyOn(gitRemoteApi, "listCredentials").mockResolvedValue([]);
    vi.spyOn(settingsApi, "get").mockResolvedValue({
      git_fetch_interval_s: 300,
    } as unknown as SettingsData);
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("«Репозиторий» без подключения предлагает подключить", () => {
    mount(
      toStatusView(NO_REMOTE_STATUS),
      <SyncRemoteSection projectId={PROJECT_ID} />,
    );
    expect(
      screen.getByRole("heading", { name: "Репозиторий" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Подключить репозиторий" }),
    ).toBeInTheDocument();
  });

  it("«Репозиторий» с подключением показывает карточку", () => {
    mount(status(), <SyncRemoteSection projectId={PROJECT_ID} />);
    expect(screen.getByTestId("remote-card")).toBeInTheDocument();
  });

  it("«Фоновая проверка» показывает выключатель", () => {
    mount(status(), <SyncOptionsSection projectId={PROJECT_ID} />);
    expect(
      screen.getByRole("heading", { name: "Фоновая проверка" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("switch", { name: "Проверять репозиторий в фоне" }),
    ).toBeInTheDocument();
  });

  it("«Папка в облачном диске» называет диск", () => {
    mount(status(), <SyncSharedFolderSection projectId={PROJECT_ID} />);
    expect(
      screen.getByRole("heading", { name: "Папка в облачном диске" }),
    ).toBeInTheDocument();
    expect(screen.getByTestId("shared-folder-warning")).toHaveTextContent(
      "Dropbox",
    );
  });

  it("«Обмен файлом» доступен и без репозитория", () => {
    mount(
      toStatusView(NO_REMOTE_STATUS),
      <SyncExchangeSection projectId={PROJECT_ID} />,
    );
    expect(
      screen.getByRole("heading", { name: "Обмен файлом" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Выгрузить…" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Выбрать файл…" }),
    ).toBeInTheDocument();
  });

  it("«Автосборка (CI)» предлагает настроить файл", () => {
    mount(
      toStatusView(NO_REMOTE_STATUS),
      <SyncCiSection projectId={PROJECT_ID} />,
    );
    expect(
      screen.getByRole("heading", { name: "Автосборка (CI)" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Настроить автосборку…" }),
    ).toBeInTheDocument();
  });
});
