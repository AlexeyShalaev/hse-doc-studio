import { cleanup, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { settingsApi, type SettingsData } from "@entities/app-settings";
import { gitRemoteApi } from "@entities/git-remote";
import {
  NO_REMOTE_STATUS,
  gitSyncApi,
  toStatusView,
  useSyncUiStore,
  type GitStatus,
  type SyncStatusView,
} from "@entities/git-sync";
import {
  PAT,
  PROJECT_ID,
  REMOTE,
  SSH_KEY,
  connectedStatus,
  noRemoteStatus,
} from "../testing/connectFixtures";
import {
  installPointerPolyfills,
  renderSettings,
  resetSettingsEnvironment,
} from "../testing/renderSettings";
import {
  FetchOptionsCard,
  RemoteConnectionCard,
  SharedFolderCard,
} from "./RemoteSettingsCards";

const APP_SETTINGS = {
  git_fetch_interval_s: 300,
} as unknown as SettingsData;

const connected = (overrides: Partial<GitStatus> = {}): SyncStatusView =>
  connectedStatus({
    ui_state: "up_to_date",
    health: "ok",
    relation: "in_sync",
    last_fetch_ok_at: "2026-10-26T10:00:00Z",
    last_sync: {
      id: "s1",
      at: "2026-10-26T09:00:00Z",
      outcome: "merged",
      pulled_commits: 3,
      pushed_commits: 2,
    },
    auto_fetch: { enabled: true, interval_s: 300, next_fetch_at: null },
    ...overrides,
  });

describe("карточка репозитория в настройках проекта", () => {
  beforeEach(async () => {
    await resetSettingsEnvironment();
    vi.spyOn(gitRemoteApi, "listCredentials").mockResolvedValue([PAT]);
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("без репозитория зовёт подключить его и открывает окно подключения", async () => {
    const user = userEvent.setup();
    renderSettings(<RemoteConnectionCard projectId={PROJECT_ID} />, {
      status: noRemoteStatus(),
    });
    expect(screen.getByText("Репозиторий не подключён")).toBeInTheDocument();
    await user.click(
      screen.getByRole("button", { name: "Подключить репозиторий" }),
    );
    expect(useSyncUiStore.getState().connectDialog).toEqual({
      mode: "connect",
    });
  });

  it("пока состояние не пришло, показывает загрузку", () => {
    vi.spyOn(gitSyncApi, "getStatus").mockReturnValue(
      new Promise<never>(() => undefined),
    );
    renderSettings(<RemoteConnectionCard projectId={PROJECT_ID} />);
    expect(screen.getByTestId("remote-settings-loading")).toBeInTheDocument();
  });

  it("при сбое загрузки даёт повторить", async () => {
    const user = userEvent.setup();
    const getStatus = vi
      .spyOn(gitSyncApi, "getStatus")
      .mockRejectedValueOnce(new Error("boom"))
      .mockResolvedValue(connected());
    renderSettings(<RemoteConnectionCard projectId={PROJECT_ID} />);
    expect(
      await screen.findByText("Не удалось получить состояние репозитория."),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Повторить" }));
    expect(await screen.findByTestId("remote-card")).toBeInTheDocument();
    expect(getStatus).toHaveBeenCalledTimes(2);
  });

  it("на старом бэкенде ничего не рисует", () => {
    const { container } = renderSettings(
      <RemoteConnectionCard projectId={PROJECT_ID} />,
      { status: toStatusView(NO_REMOTE_STATUS, false) },
    );
    expect(container.querySelector("[data-testid='remote-card']")).toBeNull();
    expect(screen.queryByTestId("remote-empty")).toBeNull();
  });

  it("показывает адрес, ветку, доступ и итог последней синхронизации", async () => {
    renderSettings(<RemoteConnectionCard projectId={PROJECT_ID} />, {
      status: connected(),
    });
    expect(screen.getByLabelText("Адрес репозитория")).toHaveValue(
      "https://github.com/hse-team/paper",
    );
    expect(screen.getByText("main")).toBeInTheDocument();
    expect(screen.getByText("GitHub, рабочий")).toBeInTheDocument();
    expect(await screen.findByText("Отклонён сервером")).toBeInTheDocument();
    expect(screen.getByText(/github_pat…/)).toBeInTheDocument();
    expect(
      screen.getByText(
        /Изменения объединены, .*Получено версий: 3, отправлено: 2/,
      ),
    ).toBeInTheDocument();
    expect(screen.getByText(/Проверено/)).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Открыть в браузере" }),
    ).toHaveAttribute("href", "https://github.com/hse-team/paper");
  });

  it("название ветки в репозитории и локальной, если они разные", () => {
    renderSettings(<RemoteConnectionCard projectId={PROJECT_ID} />, {
      status: connected({
        remote: { ...REMOTE, local_branch: "master", branch: "main" },
      }),
    });
    expect(
      screen.getByText("Локальная ветка master отправляется в main"),
    ).toBeInTheDocument();
  });

  it("если синхронизаций не было, говорит об этом", () => {
    renderSettings(<RemoteConnectionCard projectId={PROJECT_ID} />, {
      status: connected({
        last_sync: null,
        last_sync_at: null,
        last_fetch_ok_at: null,
      }),
    });
    expect(screen.getByText("Ещё не синхронизировалось")).toBeInTheDocument();
    expect(screen.getByText("Ещё не проверялось")).toBeInTheDocument();
  });

  it("«Заменить доступ» открывает окно в режиме обновления доступа", async () => {
    const user = userEvent.setup();
    renderSettings(<RemoteConnectionCard projectId={PROJECT_ID} />, {
      status: connected(),
    });
    await user.click(screen.getByRole("button", { name: "Заменить доступ" }));
    expect(useSyncUiStore.getState().connectDialog).toEqual({
      mode: "fix_access",
    });
  });

  it("публичный ключ показывается по кнопке и копируется", async () => {
    vi.spyOn(gitRemoteApi, "listCredentials").mockResolvedValue([SSH_KEY]);
    const user = userEvent.setup();
    renderSettings(<RemoteConnectionCard projectId={PROJECT_ID} />, {
      status: connected({
        remote: {
          ...REMOTE,
          kind: "ssh",
          credential: { id: "cred-ssh", label: SSH_KEY.label, kind: "ssh_key" },
        },
      }),
    });
    const toggle = await screen.findByRole("button", {
      name: "Показать публичный ключ",
    });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByLabelText("Публичный ключ")).toBeNull();
    await user.click(toggle);
    expect(screen.getByLabelText("Публичный ключ")).toHaveValue(
      SSH_KEY.public_key,
    );
    expect(
      screen.getByText(SSH_KEY.fingerprint_sha256 ?? ""),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Скрыть публичный ключ" }),
    ).toHaveAttribute("aria-expanded", "true");
  });

  it("у репозитория без доступа объясняет, что токена нет", () => {
    renderSettings(<RemoteConnectionCard projectId={PROJECT_ID} />, {
      status: connected({ remote: { ...REMOTE, credential: null } }),
    });
    expect(screen.getByTestId("remote-no-credential")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Заменить доступ" }),
    ).toBeNull();
  });

  it("«Синхронизировать сейчас» ставит команду в очередь", async () => {
    const user = userEvent.setup();
    renderSettings(<RemoteConnectionCard projectId={PROJECT_ID} />, {
      status: connected(),
    });
    await user.click(
      screen.getByRole("button", { name: "Синхронизировать сейчас" }),
    );
    expect(useSyncUiStore.getState().command?.kind).toBe("sync");
    await user.click(
      screen.getByRole("button", { name: "Проверить обновления" }),
    );
    expect(useSyncUiStore.getState().command?.kind).toBe("check");
  });

  it("пока идёт синхронизация, кнопки выключены", () => {
    renderSettings(<RemoteConnectionCard projectId={PROJECT_ID} />, {
      status: connected({
        ui_state: "syncing",
        operation: {
          id: "op-1",
          kind: "sync",
          phase: "fetch",
          percent: 30,
          cancellable: true,
          started_at: "2026-10-26T10:00:00Z",
        },
      }),
    });
    expect(
      screen.getByRole("button", { name: /Идёт синхронизация/ }),
    ).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "Проверить обновления" }),
    ).toBeDisabled();
  });

  it("при конфликтах вместо синхронизации предлагает их разобрать", async () => {
    const user = userEvent.setup();
    renderSettings(<RemoteConnectionCard projectId={PROJECT_ID} />, {
      status: connected({
        ui_state: "conflicts",
        pending: { session_id: "c1", files_total: 3, files_open: 2 },
      }),
    });
    expect(
      screen.queryByRole("button", { name: "Синхронизировать сейчас" }),
    ).toBeNull();
    await user.click(
      screen.getByRole("button", { name: "Разобрать конфликты" }),
    );
    expect(screen.getByTestId("location")).toHaveTextContent(
      `/projects/${PROJECT_ID}/sync/conflicts`,
    );
  });

  it("если синхронизация заблокирована, называет причину и не запускает её", () => {
    renderSettings(<RemoteConnectionCard projectId={PROJECT_ID} />, {
      status: connected({
        ui_state: "blocked",
        blocked: { reason: "off_branch", required_studio: null },
      }),
    });
    expect(
      screen.getByText("Проект открыт не на ветке, которая синхронизируется."),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Синхронизировать сейчас" }),
    ).toBeDisabled();
  });

  it("при отсутствии автора просит открыть окно «Представься»", async () => {
    const user = userEvent.setup();
    renderSettings(<RemoteConnectionCard projectId={PROJECT_ID} />, {
      status: connected({
        ui_state: "blocked",
        blocked: { reason: "profile_required", required_studio: null },
      }),
    });
    await user.click(screen.getByRole("button", { name: "Указать автора" }));
    expect(useSyncUiStore.getState().profileDialogOpen).toBe(true);
  });

  it("отказ входа показывает причину и ведёт к замене доступа", async () => {
    const user = userEvent.setup();
    renderSettings(<RemoteConnectionCard projectId={PROJECT_ID} />, {
      status: connected({
        ui_state: "auth_failed",
        health: "unauthenticated",
        last_error: {
          code: "auth_failed",
          detail: "Сервер отклонил токен.",
          at: "2026-10-26T10:00:00Z",
        },
      }),
    });
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent(/отклонил|доступ/i);
    await user.click(
      within(alert).getByRole("button", { name: "Заменить доступ" }),
    );
    expect(useSyncUiStore.getState().connectDialog?.mode).toBe("fix_access");
  });

  it("адрес без шифрования сопровождается предупреждением", () => {
    renderSettings(<RemoteConnectionCard projectId={PROJECT_ID} />, {
      status: connected({
        remote: {
          ...REMOTE,
          kind: "http",
          display_url: "http://git.local/team/paper",
          insecure_http: true,
        },
      }),
    });
    expect(screen.getByText(/без шифрования \(http\)/)).toBeInTheDocument();
  });

  it("английский язык: те же состояния, другие слова", async () => {
    const { i18n } = await import("@shared/lib/i18n");
    await i18n.changeLanguage("en");
    renderSettings(<RemoteConnectionCard projectId={PROJECT_ID} />, {
      status: connected(),
    });
    expect(
      screen.getByRole("button", { name: "Sync now" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Disconnect" }),
    ).toBeInTheDocument();
    await i18n.changeLanguage("ru");
  });
});

describe("отключение репозитория из карточки", () => {
  beforeEach(async () => {
    await resetSettingsEnvironment();
    vi.spyOn(gitRemoteApi, "listCredentials").mockResolvedValue([PAT]);
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("кнопка в опасной зоне открывает окно подтверждения", async () => {
    const user = userEvent.setup();
    renderSettings(<RemoteConnectionCard projectId={PROJECT_ID} />, {
      status: connected(),
    });
    expect(screen.queryByRole("dialog")).toBeNull();
    await user.click(screen.getByRole("button", { name: "Отключить" }));
    expect(
      screen.getByRole("dialog", { name: "Отключить репозиторий?" }),
    ).toBeInTheDocument();
  });
});

describe("фоновая проверка в настройках проекта", () => {
  beforeEach(async () => {
    await resetSettingsEnvironment();
    installPointerPolyfills();
    vi.spyOn(settingsApi, "get").mockResolvedValue(APP_SETTINGS);
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("без репозитория ничего не рисует", () => {
    const { container } = renderSettings(
      <FetchOptionsCard projectId={PROJECT_ID} />,
      { status: noRemoteStatus() },
    );
    expect(container.querySelector("[data-testid='fetch-options']")).toBeNull();
  });

  it("показывает включённый выключатель и интервал по умолчанию", async () => {
    renderSettings(<FetchOptionsCard projectId={PROJECT_ID} />, {
      status: connected(),
    });
    expect(
      screen.getByRole("switch", { name: "Проверять репозиторий в фоне" }),
    ).toHaveAttribute("aria-checked", "true");
    expect(
      await screen.findByRole("combobox", { name: "Как часто проверять" }),
    ).toHaveTextContent("Как по умолчанию (5 мин)");
    expect(
      screen.getByText(/Это личные настройки Студии на этом компьютере/),
    ).toBeInTheDocument();
  });

  it("выключатель отправляет auto_fetch и сразу показывает новое состояние", async () => {
    const user = userEvent.setup();
    const update = vi.spyOn(gitSyncApi, "updateSettings").mockResolvedValue({
      ...connected(),
      auto_fetch: { enabled: false, interval_s: 300, next_fetch_at: null },
    });
    renderSettings(<FetchOptionsCard projectId={PROJECT_ID} />, {
      status: connected(),
    });
    await user.click(
      screen.getByRole("switch", { name: "Проверять репозиторий в фоне" }),
    );
    await waitFor(() => {
      expect(update).toHaveBeenCalledWith(PROJECT_ID, { auto_fetch: false });
    });
    await waitFor(() => {
      expect(
        screen.getByRole("switch", { name: "Проверять репозиторий в фоне" }),
      ).toHaveAttribute("aria-checked", "false");
    });
    expect(
      screen.getByRole("combobox", { name: "Как часто проверять" }),
    ).toBeDisabled();
  });

  it("выбор интервала отправляет секунды, «по умолчанию» отправляет null", async () => {
    const user = userEvent.setup();
    const update = vi.spyOn(gitSyncApi, "updateSettings").mockResolvedValue(
      connected({
        auto_fetch: { enabled: true, interval_s: 900, next_fetch_at: null },
      }),
    );
    renderSettings(<FetchOptionsCard projectId={PROJECT_ID} />, {
      status: connected(),
    });
    await user.click(
      await screen.findByRole("combobox", { name: "Как часто проверять" }),
    );
    await user.click(await screen.findByRole("option", { name: "15 мин" }));
    await waitFor(() => {
      expect(update).toHaveBeenCalledWith(PROJECT_ID, { interval_s: 900 });
    });

    await waitFor(() => {
      expect(
        screen.getByRole("combobox", { name: "Как часто проверять" }),
      ).toHaveTextContent("15 мин");
    });
    await user.click(
      screen.getByRole("combobox", { name: "Как часто проверять" }),
    );
    await user.click(
      await screen.findByRole("option", { name: "Как по умолчанию (5 мин)" }),
    );
    await waitFor(() => {
      expect(update).toHaveBeenLastCalledWith(PROJECT_ID, { interval_s: null });
    });
  });

  it("нестандартный интервал проекта остаётся в списке и выбран", async () => {
    renderSettings(<FetchOptionsCard projectId={PROJECT_ID} />, {
      status: connected({
        auto_fetch: { enabled: true, interval_s: 450, next_fetch_at: null },
      }),
    });
    expect(
      await screen.findByRole("combobox", { name: "Как часто проверять" }),
    ).toHaveTextContent("8 мин");
  });

  it("называет время следующей проверки, а без него последней", () => {
    renderSettings(<FetchOptionsCard projectId={PROJECT_ID} />, {
      status: connected({
        auto_fetch: {
          enabled: true,
          interval_s: 300,
          next_fetch_at: new Date(Date.now() + 3 * 60_000).toISOString(),
        },
      }),
    });
    expect(screen.getByText(/Следующая проверка/)).toBeInTheDocument();
    cleanup();
    renderSettings(<FetchOptionsCard projectId={PROJECT_ID} />, {
      status: connected(),
    });
    expect(screen.getByText(/Последняя проверка/)).toBeInTheDocument();
  });

  it("сбой сохранения показывается заметкой", async () => {
    const user = userEvent.setup();
    vi.spyOn(gitSyncApi, "updateSettings").mockRejectedValue(new Error("x"));
    renderSettings(<FetchOptionsCard projectId={PROJECT_ID} />, {
      status: connected(),
    });
    await user.click(
      screen.getByRole("switch", { name: "Проверять репозиторий в фоне" }),
    );
    expect(
      await screen.findByText("Не удалось сохранить настройку."),
    ).toBeInTheDocument();
  });

  it("ссылка на настройку по умолчанию ведёт в раздел доступа", async () => {
    const user = userEvent.setup();
    renderSettings(<FetchOptionsCard projectId={PROJECT_ID} />, {
      status: connected(),
    });
    await user.click(
      screen.getByRole("button", {
        name: "Интервал по умолчанию",
      }),
    );
    expect(screen.getByTestId("location")).toHaveTextContent(
      "/settings/git-access",
    );
  });
});

describe("папка проекта в облачном диске", () => {
  beforeEach(async () => {
    await resetSettingsEnvironment();
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  const shared = (acknowledged: boolean): SyncStatusView =>
    connected({
      shared_folder: {
        provider: "yandex_disk",
        root: "/Users/ivan/Yandex.Disk",
        acknowledged,
      },
    });

  it("без обнаруженного диска карточка пуста", () => {
    const { container } = renderSettings(
      <SharedFolderCard projectId={PROJECT_ID} />,
      { status: connected() },
    );
    expect(
      container.querySelector("[data-testid='shared-folder-card']"),
    ).toBeNull();
  });

  it("называет диск, папку и риск", () => {
    renderSettings(<SharedFolderCard projectId={PROJECT_ID} />, {
      status: shared(false),
    });
    expect(
      screen.getByText("Папка проекта лежит в Яндекс.Диск"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Диск: \/Users\/ivan\/Yandex.Disk/),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("switch", { name: "Я знаю об этом, не напоминать" }),
    ).toHaveAttribute("aria-checked", "false");
  });

  it("выключатель подтверждения отправляет shared_folder_ack в обе стороны", async () => {
    const user = userEvent.setup();
    const update = vi
      .spyOn(gitSyncApi, "updateSettings")
      .mockResolvedValueOnce(shared(true))
      .mockResolvedValueOnce(shared(false));
    renderSettings(<SharedFolderCard projectId={PROJECT_ID} />, {
      status: shared(false),
    });
    const toggle = screen.getByRole("switch", {
      name: "Я знаю об этом, не напоминать",
    });
    await user.click(toggle);
    await waitFor(() => {
      expect(update).toHaveBeenCalledWith(PROJECT_ID, {
        shared_folder_ack: true,
      });
    });
    await waitFor(() => {
      expect(toggle).toHaveAttribute("aria-checked", "true");
    });
    await user.click(toggle);
    await waitFor(() => {
      expect(update).toHaveBeenLastCalledWith(PROJECT_ID, {
        shared_folder_ack: false,
      });
    });
  });
});
