import { act, cleanup, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@shared/api";
import { useToastStore } from "@shared/lib";
import { i18n } from "@shared/lib/i18n";
import { gitRemoteApi, type GitCredentialCheck } from "@entities/git-remote";
import { gitSyncApi, useSyncUiStore } from "@entities/git-sync";
import { profileApi } from "@entities/profile";
import {
  CHECK_OK,
  CONTENTS,
  CUSTOM_PROFILE,
  DEFAULT_PROFILE,
  PAT,
  PROBE_PROJECT,
  PROJECT_ID,
  REMOTE,
  SSH_KEY,
  connectedStatus,
  failedProbe,
  makeProbe,
  noRemoteStatus,
} from "../testing/connectFixtures";
import {
  openConnectDialog,
  renderWithClient,
  resetConnectEnvironment,
} from "../testing/renderConnect";

const project = { meta: {} as Record<string, unknown> };
vi.mock("@entities/project", async () => ({
  ...(await vi.importActual<Record<string, unknown>>("@entities/project")),
  useProject: () => ({ data: project }),
}));

import { ConnectRemoteDialog } from "./ConnectRemoteDialog";

const TOKEN = "github_pat_SECRET_TOKEN_VALUE_123";

type Setup = {
  status?: ReturnType<typeof noRemoteStatus>;
  profile?: typeof CUSTOM_PROFILE;
  contents?: typeof CONTENTS;
  credentials?: (typeof PAT)[];
};

const setup = (options: Setup = {}) => {
  vi.spyOn(gitSyncApi, "getStatus").mockResolvedValue(
    options.status ?? noRemoteStatus(),
  );
  vi.spyOn(gitSyncApi, "getContents").mockResolvedValue(
    options.contents ?? CONTENTS,
  );
  vi.spyOn(profileApi, "get").mockResolvedValue(
    options.profile ?? CUSTOM_PROFILE,
  );
  vi.spyOn(gitRemoteApi, "listCredentials").mockResolvedValue(
    options.credentials ?? [],
  );
  vi.spyOn(gitRemoteApi, "getSecretsStatus").mockResolvedValue({
    ok: true,
    source: "file",
    permissions_enforced: true,
    credentials_total: 0,
    credentials_unreadable: 0,
    data_dir_shared_folder: null,
  });
  vi.spyOn(gitRemoteApi, "listHosts").mockResolvedValue([]);
  vi.spyOn(gitRemoteApi, "listHostSettings").mockResolvedValue([]);
  vi.spyOn(gitRemoteApi, "checkCredential").mockResolvedValue(CHECK_OK);
  const probe = vi
    .spyOn(gitRemoteApi, "probe")
    .mockResolvedValue(makeProbe({ relation: "empty", empty: true }));
  const connect = vi
    .spyOn(gitSyncApi, "connectRemote")
    .mockResolvedValue(connectedStatus({ ui_state: "ahead", health: "ok" }));
  const startSync = vi
    .spyOn(gitSyncApi, "startSync")
    .mockResolvedValue({ operation_id: "op-1" });
  const createCredential = vi
    .spyOn(gitRemoteApi, "createCredential")
    .mockResolvedValue({ ...PAT, status: "unverified" });
  return { probe, connect, startSync, createCredential };
};

// Сервер вернёт созданный доступ и при следующем чтении списка.
const savesCredential = (
  createCredential: ReturnType<typeof setup>["createCredential"],
  credential: typeof PAT,
): void => {
  createCredential.mockImplementation(() => {
    vi.mocked(gitRemoteApi.listCredentials).mockResolvedValue([credential]);
    return Promise.resolve(credential);
  });
};

const mount = (
  mode: "connect" | "fix_access" = "connect",
  onClone?: () => void,
) => {
  const view = renderWithClient(
    <ConnectRemoteDialog
      projectId={PROJECT_ID}
      {...(onClone ? { onCloneInstead: onClone } : {})}
    />,
  );
  act(() => {
    openConnectDialog(mode);
  });
  return view;
};

const urlInput = () => screen.getByLabelText("Адрес репозитория");
const next = () => screen.getByRole("button", { name: "Далее" });

const typeUrl = async (
  user: ReturnType<typeof userEvent.setup>,
  url: string,
) => {
  await user.click(await screen.findByLabelText("Адрес репозитория"));
  await user.paste(url);
};

// Проходит шаги 1 и 2 токеном и ждёт итог проверки.
const goThroughToken = async (
  user: ReturnType<typeof userEvent.setup>,
  url = "https://github.com/hse-team/paper",
) => {
  await typeUrl(user, url);
  await user.click(next());
  await user.click(await screen.findByLabelText("Токен"));
  await user.keyboard(TOKEN);
  await user.click(
    screen.getByRole("button", { name: "Сохранить и проверить" }),
  );
};

describe("ConnectRemoteDialog: шаг «Репозиторий»", () => {
  beforeEach(async () => {
    await resetConnectEnvironment();
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("закрыт, пока не попросили его открыть", () => {
    setup();
    renderWithClient(<ConnectRemoteDialog projectId={PROJECT_ID} />);
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("открывается на адресе: «Далее» выключено, пока адрес не разобран", async () => {
    setup();
    const user = userEvent.setup();
    mount();
    expect(
      await screen.findByRole("dialog", { name: "Подключить репозиторий" }),
    ).toBeInTheDocument();
    expect(await screen.findByLabelText("Адрес репозитория")).toHaveFocus();
    expect(next()).toBeDisabled();
    expect(
      within(screen.getByRole("list", { name: "Шаги подключения" }))
        .getByText("Репозиторий")
        .closest("li"),
    ).toHaveAttribute("aria-current", "step");

    await user.paste("https://github.com/hse-team/paper.git");
    expect(next()).toBeEnabled();
    const chip = screen.getByTestId("provider-chip");
    expect(chip).toHaveTextContent("GitHub");
    expect(chip).toHaveTextContent("hse-team/paper");
  });

  it("ругается на тип адреса сразу, а на «не похоже» после ухода из поля", async () => {
    setup();
    const user = userEvent.setup();
    mount();
    await typeUrl(user, "git://github.com/hse/paper.git");
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Используй https или ssh",
    );
    await user.clear(urlInput());
    await user.type(urlInput(), "что-то не то");
    expect(screen.queryByRole("alert")).toBeNull();
    await user.tab();
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Адрес репозитория не похож на корректный",
    );
    expect(next()).toBeDisabled();
  });

  it("убирает токен из адреса и говорит об этом, а в проверку токен не уходит", async () => {
    const { probe } = setup();
    const user = userEvent.setup();
    mount();
    await typeUrl(user, "https://ghp_LEAKED123@github.com/hse-team/paper.git");
    expect(screen.getByText(/Токен в адресе не нужен/)).toBeInTheDocument();
    // Сообщение «убрали» правдиво: токена нет и в самом поле.
    expect(urlInput()).toHaveValue("https://github.com/hse-team/paper.git");
    await user.click(next());
    await user.click(await screen.findByLabelText("Токен"));
    await user.keyboard(TOKEN);
    await user.click(
      screen.getByRole("button", { name: "Сохранить и проверить" }),
    );
    await waitFor(() => {
      expect(probe).toHaveBeenCalled();
    });
    expect(JSON.stringify(probe.mock.calls)).not.toContain("LEAKED123");
    expect(probe.mock.calls[0]?.[0].url).toBe(
      "https://github.com/hse-team/paper.git",
    );
  });

  it("крупные файлы в истории не дают идти дальше", async () => {
    setup({
      contents: {
        ...CONTENTS,
        over_limit: [
          {
            path: "video/rehearsal.mov",
            bytes: 190 * 1024 * 1024,
            limit: 95 * 1024 * 1024,
          },
        ],
      },
    });
    const user = userEvent.setup();
    mount();
    await typeUrl(user, "https://github.com/hse-team/paper");
    const blocker = await screen.findByTestId("over-limit");
    expect(blocker).toHaveTextContent("1 файл крупнее лимита сервера");
    expect(blocker).toHaveTextContent("video/rehearsal.mov");
    expect(next()).toBeDisabled();
  });

  it("NDA: без подтверждения условий дальше нельзя", async () => {
    setup({ contents: { ...CONTENTS, nda_files: 2 } });
    const user = userEvent.setup();
    mount();
    await typeUrl(user, "https://github.com/hse-team/paper");
    expect(await screen.findByText("Проект помечен NDA")).toBeInTheDocument();
    expect(next()).toBeDisabled();
    await user.click(screen.getByTestId("nda-confirm"));
    expect(next()).toBeEnabled();
  });

  it("предупреждает про прежние версии без автора, LFS и показывает состав", async () => {
    setup({
      contents: { ...CONTENTS, bot_authored_commits: 14, lfs_pointers: 3 },
    });
    const user = userEvent.setup();
    mount();
    expect(
      await screen.findByText(/14 прежних версий подписаны общей подписью/),
    ).toBeInTheDocument();
    expect(screen.getByText(/Найдено 3 файла Git LFS/)).toBeInTheDocument();
    const details = screen.getByTestId("contents-details");
    await user.click(within(details).getByText("Что попадёт в репозиторий"));
    expect(details).toHaveTextContent("86 файлов");
    expect(details).toHaveTextContent("142 версии");
    expect(details).toHaveTextContent("images/architecture.png");
  });

  it("предупреждение про облачный диск не мешает и запоминается кнопкой", async () => {
    const updateSettings = vi
      .spyOn(gitSyncApi, "updateSettings")
      .mockResolvedValue(noRemoteStatus());
    setup({
      status: noRemoteStatus({
        shared_folder: {
          provider: "yandex_disk",
          root: "/Users/ivan/Yandex.Disk",
          acknowledged: false,
        },
      }),
    });
    const user = userEvent.setup();
    mount();
    const warning = await screen.findByTestId("shared-folder-warning");
    expect(warning).toHaveTextContent("Папка проекта лежит в Яндекс.Диск");
    await typeUrl(user, "https://github.com/hse-team/paper");
    expect(next()).toBeEnabled();
    await user.click(within(warning).getByRole("button", { name: "Понятно" }));
    expect(updateSettings).toHaveBeenCalledWith(PROJECT_ID, {
      shared_folder_ack: true,
    });
  });

  it("«Отмена» закрывает окно", async () => {
    setup();
    const user = userEvent.setup();
    mount();
    await screen.findByLabelText("Адрес репозитория");
    await user.click(screen.getByRole("button", { name: "Отмена" }));
    await waitFor(() => {
      expect(useSyncUiStore.getState().connectDialog).toBeNull();
    });
  });
});

describe("ConnectRemoteDialog: профиль автора", () => {
  beforeEach(async () => {
    await resetConnectEnvironment();
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("без имени и e-mail сначала просит представиться, потом идёт к адресу", async () => {
    setup({ profile: DEFAULT_PROFILE });
    const update = vi
      .spyOn(profileApi, "update")
      .mockResolvedValue(CUSTOM_PROFILE);
    const user = userEvent.setup();
    mount();
    expect(await screen.findByLabelText("Имя")).toBeInTheDocument();
    expect(screen.queryByLabelText("Адрес репозитория")).toBeNull();
    expect(screen.getByText(/Сначала представься/)).toBeInTheDocument();

    await user.type(screen.getByLabelText("Имя"), "Иван Смирнов");
    await user.type(screen.getByLabelText("E-mail"), "ivan@edu.hse.ru");
    await user.click(
      screen.getByRole("button", { name: "Сохранить и продолжить" }),
    );
    expect(update).toHaveBeenCalledWith({
      name: "Иван Смирнов",
      email: "ivan@edu.hse.ru",
    });
    expect(
      await screen.findByLabelText("Адрес репозитория"),
    ).toBeInTheDocument();
  });
});

describe("ConnectRemoteDialog: шаг «Доступ»", () => {
  beforeEach(async () => {
    await resetConnectEnvironment();
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("токен: сохраняется, поле очищается, в проверку и в страницу он не попадает", async () => {
    const { createCredential, probe } = setup();
    const user = userEvent.setup();
    mount();
    await typeUrl(user, "https://github.com/hse-team/paper");
    await user.click(next());

    const field = await screen.findByLabelText("Токен");
    expect(field).toHaveAttribute("type", "password");
    expect(field).toHaveAttribute("autocomplete", "off");
    await user.click(field);
    await user.keyboard(TOKEN);
    expect(field).toHaveValue(TOKEN);

    // Показать и спрятать.
    await user.click(screen.getByRole("button", { name: "Показать токен" }));
    expect(field).toHaveAttribute("type", "text");
    await user.click(screen.getByRole("button", { name: "Скрыть токен" }));
    expect(field).toHaveAttribute("type", "password");

    await user.click(
      screen.getByRole("button", { name: "Сохранить и проверить" }),
    );
    await waitFor(() => {
      expect(createCredential).toHaveBeenCalledWith({
        kind: "pat",
        label: "GitHub, github.com",
        host: "github.com",
        token: TOKEN,
      });
    });
    await waitFor(() => {
      expect(probe).toHaveBeenCalledWith({
        url: "https://github.com/hse-team/paper",
        credential_id: PAT.id,
        project_id: PROJECT_ID,
      });
    });
    // Токен нигде не остался: ни в проверке, ни в разметке.
    expect(JSON.stringify(probe.mock.calls)).not.toContain(TOKEN);
    expect(document.body.innerHTML).not.toContain(TOKEN);
    expect(
      Array.from(document.querySelectorAll("input")).map((i) => i.value),
    ).not.toContain(TOKEN);
  });

  it("отказ при сохранении очищает токен и объясняет причину", async () => {
    const { createCredential } = setup();
    createCredential.mockRejectedValue(
      new ApiError("Хранилище", "secrets_unavailable", 409),
    );
    const user = userEvent.setup();
    mount();
    await typeUrl(user, "https://github.com/hse-team/paper");
    await user.click(next());
    const field = await screen.findByLabelText("Токен");
    await user.click(field);
    await user.keyboard(TOKEN);
    await user.click(
      screen.getByRole("button", { name: "Сохранить и проверить" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Хранилище секретов недоступно, сохранённые токены не читаются.",
    );
    expect(screen.getByLabelText("Токен")).toHaveValue("");
    expect(document.body.innerHTML).not.toContain(TOKEN);
  });

  it("кнопка выключена, пока токен пуст", async () => {
    setup();
    const user = userEvent.setup();
    mount();
    await typeUrl(user, "https://github.com/hse-team/paper");
    await user.click(next());
    await screen.findByLabelText("Токен");
    expect(
      screen.getByRole("button", { name: "Сохранить и проверить" }),
    ).toBeDisabled();
  });

  it("сохранённый токен для этого сервера выбирается без создания нового", async () => {
    const { createCredential, probe } = setup({
      credentials: [{ ...PAT, status: "ok" }],
    });
    const user = userEvent.setup();
    mount();
    await typeUrl(user, "https://github.com/hse-team/paper");
    await user.click(next());
    const picker = await screen.findByTestId("credential-picker");
    expect(within(picker).getByLabelText(/GitHub, рабочий/)).toBeChecked();
    // Форма нового токена не показана, пока выбран сохранённый.
    expect(screen.queryByTestId("pat-panel")).toBeNull();
    await user.click(screen.getByRole("button", { name: "Проверить" }));
    await waitFor(() => {
      expect(probe).toHaveBeenCalledWith({
        url: "https://github.com/hse-team/paper",
        credential_id: PAT.id,
        project_id: PROJECT_ID,
      });
    });
    expect(createCredential).not.toHaveBeenCalled();
  });

  it("можно добавить новый токен рядом с сохранённым", async () => {
    setup({ credentials: [{ ...PAT, status: "ok" }] });
    const user = userEvent.setup();
    mount();
    await typeUrl(user, "https://github.com/hse-team/paper");
    await user.click(next());
    await user.click(await screen.findByLabelText("Добавить новый токен"));
    expect(screen.getByTestId("pat-panel")).toBeInTheDocument();
  });

  it("ssh: создаёт ключ, показывает публичную часть и отпечаток, копирует", async () => {
    const { createCredential } = setup();
    savesCredential(createCredential, SSH_KEY);
    const user = userEvent.setup();
    mount();
    await typeUrl(user, "git@github.com:hse-team/paper.git");
    await user.click(next());
    // Для ssh-адреса сразу открыт способ «ключ Студии».
    expect(
      await screen.findByRole("tab", { name: /Ключ Студии/, selected: true }),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Создать ключ" }));
    await waitFor(() => {
      expect(createCredential).toHaveBeenCalledWith({
        kind: "ssh_key",
        label: "Ключ: GitHub, github.com",
        host: "github.com",
      });
    });
    const keyField = await screen.findByLabelText("Публичный ключ", {
      selector: "textarea",
    });
    expect(keyField).toHaveValue(SSH_KEY.public_key);
    expect(screen.getByTestId("ssh-fingerprint")).toHaveTextContent(
      SSH_KEY.fingerprint_sha256 ?? "",
    );
    // Ключ пользователя добавляется на странице ключей профиля.
    expect(
      screen.getByRole("link", { name: /Открыть страницу ключей GitHub/ }),
    ).toHaveAttribute("href", "https://github.com/settings/keys");
    expect(screen.queryByText(/Allow write access/)).toBeNull();

    await user.click(screen.getByRole("button", { name: /Копировать/ }));
    expect(await navigator.clipboard.readText()).toBe(SSH_KEY.public_key);
    expect(
      await screen.findByRole("button", { name: /Скопировано/ }),
    ).toBeInTheDocument();
  });

  it("токен при ssh-адресе: подсказка и замена адреса на https", async () => {
    setup();
    const user = userEvent.setup();
    mount();
    await typeUrl(user, "git@github.com:hse-team/paper.git");
    await user.click(next());
    await user.click(
      await screen.findByRole("tab", { name: /Токен \(HTTPS\)/ }),
    );
    expect(
      screen.getByText(/Токен работает только с https-адресом/),
    ).toBeInTheDocument();
    await user.click(
      screen.getByRole("button", {
        name: "Заменить адрес на https://github.com/hse-team/paper.git",
      }),
    );
    expect(
      screen.queryByText(/Токен работает только с https-адресом/),
    ).toBeNull();
  });

  it("входа через браузер нет: ни карточки, ни обещания", async () => {
    setup();
    const user = userEvent.setup();
    mount();
    await typeUrl(user, "https://github.com/hse-team/paper");
    await user.click(next());
    await screen.findByTestId("pat-panel");
    expect(screen.queryByTestId("browser-login-card")).toBeNull();
    expect(screen.queryByText(/Скоро/)).toBeNull();
  });

  it("недоступное хранилище секретов запрещает сохранять токен", async () => {
    setup();
    vi.spyOn(gitRemoteApi, "getSecretsStatus").mockResolvedValue({
      ok: false,
      source: "file",
      permissions_enforced: true,
      credentials_total: 1,
      credentials_unreadable: 1,
      data_dir_shared_folder: null,
    });
    const user = userEvent.setup();
    mount();
    await typeUrl(user, "https://github.com/hse-team/paper");
    await user.click(next());
    expect(
      await screen.findByText(/Хранилище секретов недоступно: токены и ключи/),
    ).toBeInTheDocument();
    await user.click(screen.getByLabelText("Токен"));
    await user.keyboard(TOKEN);
    expect(
      screen.getByRole("button", { name: "Сохранить и проверить" }),
    ).toBeDisabled();
  });

  it("«Назад» возвращает к адресу, введённое сохраняется", async () => {
    setup();
    const user = userEvent.setup();
    mount();
    await typeUrl(user, "https://github.com/hse-team/paper");
    await user.click(next());
    await user.click(await screen.findByRole("button", { name: "Назад" }));
    expect(await screen.findByLabelText("Адрес репозитория")).toHaveValue(
      "https://github.com/hse-team/paper",
    );
  });
});

describe("ConnectRemoteDialog: шаг «Проверка»", () => {
  beforeEach(async () => {
    await resetConnectEnvironment();
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("пустой репозиторий: подключает и сразу синхронизирует", async () => {
    const { connect, startSync } = setup();
    const user = userEvent.setup();
    mount();
    await goThroughToken(user);
    const card = await screen.findByTestId("probe-result-ready-empty");
    expect(card).toHaveTextContent("Репозиторий пуст");
    expect(card).toHaveTextContent("86 файлов");
    expect(card).toHaveTextContent("142 версии");
    // Все четыре строки чек-листа пройдены.
    const list = screen.getByTestId("probe-checklist");
    expect(list.querySelectorAll('li[data-state="done"]')).toHaveLength(4);

    await user.click(
      within(card).getByRole("button", {
        name: "Подключить и синхронизировать",
      }),
    );
    await waitFor(() => {
      expect(connect).toHaveBeenCalledWith(PROJECT_ID, {
        url: "https://github.com/hse-team/paper",
        credential_id: PAT.id,
      });
    });
    await waitFor(() => {
      expect(startSync).toHaveBeenCalledWith(PROJECT_ID);
    });
    await waitFor(() => {
      expect(useSyncUiStore.getState().connectDialog).toBeNull();
    });
    expect(useSyncUiStore.getState().popoverOpen).toBe(true);
    expect(useToastStore.getState().toasts.map((t) => t.message)).toContain(
      "Проект подключён к hse-team/paper. Начинаем первую синхронизацию.",
    );
  });

  it("«Только подключить» не запускает синхронизацию и не открывает панель", async () => {
    const { connect, startSync } = setup();
    const user = userEvent.setup();
    mount();
    await goThroughToken(user);
    await user.click(
      await screen.findByRole("button", { name: "Только подключить" }),
    );
    await waitFor(() => {
      expect(connect).toHaveBeenCalled();
    });
    await waitFor(() => {
      expect(useSyncUiStore.getState().connectDialog).toBeNull();
    });
    expect(startSync).not.toHaveBeenCalled();
    expect(useSyncUiStore.getState().popoverOpen).toBe(false);
  });

  it("введённая ветка уходит и в проверку, и в подключение", async () => {
    const { probe, connect } = setup();
    probe.mockResolvedValue(makeProbe());
    const user = userEvent.setup();
    mount();
    await typeUrl(user, "https://github.com/hse-team/paper");
    await user.type(screen.getByLabelText(/Ветка в репозитории/), "develop");
    await user.click(next());
    await user.click(await screen.findByLabelText("Токен"));
    await user.keyboard(TOKEN);
    await user.click(
      screen.getByRole("button", { name: "Сохранить и проверить" }),
    );
    const card = await screen.findByTestId("probe-result-ready-same");
    expect(card).toHaveTextContent("В репозитории уже есть этот проект");
    expect(card).toHaveTextContent("Курсовая работа");
    expect(card).toHaveTextContent("coursework 1.2.0");
    expect(probe.mock.calls[0]?.[0].branch).toBe("develop");
    await user.click(
      within(card).getByRole("button", { name: "Только подключить" }),
    );
    await waitFor(() => {
      expect(connect).toHaveBeenCalledWith(PROJECT_ID, {
        url: "https://github.com/hse-team/paper",
        credential_id: PAT.id,
        remote_branch: "develop",
      });
    });
  });

  it("новее Студии: подключить можно, но предупреждает", async () => {
    const { probe } = setup();
    probe.mockResolvedValue(
      makeProbe({ schema_access: "read_only", required_studio: "0.4.0" }),
    );
    const user = userEvent.setup();
    mount();
    await goThroughToken(user);
    const card = await screen.findByTestId("probe-result-ready-same");
    expect(card).toHaveTextContent("создан более новой версией Студии");
    expect(card).toHaveTextContent("Нужна версия 0.4.0.");
    expect(
      within(card).getByRole("button", { name: "Только подключить" }),
    ).toBeEnabled();
  });

  it("отдельная история: объединить можно только после подтверждения", async () => {
    const { probe, connect } = setup();
    probe.mockResolvedValue(
      makeProbe({ relation: "same_project_unrelated_history" }),
    );
    const user = userEvent.setup();
    mount();
    await goThroughToken(user);
    const card = await screen.findByTestId("probe-result-unrelated");
    expect(card).toHaveTextContent("нет общей истории");
    const adopt = within(card).getByRole("button", {
      name: "Объединить и подключить",
    });
    expect(adopt).toBeDisabled();
    // Последняя строка чек-листа не пройдена.
    expect(
      screen
        .getByTestId("probe-checklist")
        .querySelectorAll('li[data-state="error"]'),
    ).toHaveLength(1);
    await user.click(screen.getByTestId("adopt-confirm"));
    expect(adopt).toBeEnabled();
    await user.click(adopt);
    await waitFor(() => {
      expect(connect).toHaveBeenCalledWith(PROJECT_ID, {
        url: "https://github.com/hse-team/paper",
        credential_id: PAT.id,
        adopt: "merge_remote",
      });
    });
  });

  it("другой проект: нельзя подключить, предлагает клонирование, если оно есть", async () => {
    const { probe } = setup();
    probe.mockResolvedValue(
      makeProbe({
        relation: "other_project",
        project: { ...PROBE_PROJECT, name: "Чужой проект" },
      }),
    );
    const onClone = vi.fn();
    const user = userEvent.setup();
    mount("connect", onClone);
    await goThroughToken(user);
    const card = await screen.findByTestId("probe-result-other_project");
    expect(card).toHaveTextContent("Чужой проект");
    expect(
      within(card).queryByRole("button", { name: /Подключить/ }),
    ).toBeNull();
    await user.click(
      within(card).getByRole("button", { name: "Клонировать в новую папку" }),
    );
    expect(onClone).toHaveBeenCalledWith({
      url: "https://github.com/hse-team/paper",
      credentialId: PAT.id,
    });
    await waitFor(() => {
      expect(useSyncUiStore.getState().connectDialog).toBeNull();
    });
  });

  it("без обработчика клонирования кнопки нет, остаётся выбор другого репозитория", async () => {
    const { probe } = setup();
    probe.mockResolvedValue(makeProbe({ relation: "other_project" }));
    const user = userEvent.setup();
    mount();
    await goThroughToken(user);
    const card = await screen.findByTestId("probe-result-other_project");
    expect(
      within(card).queryByRole("button", { name: "Клонировать в новую папку" }),
    ).toBeNull();
    await user.click(
      within(card).getByRole("button", { name: "Выбрать другой репозиторий" }),
    );
    expect(
      await screen.findByLabelText("Адрес репозитория"),
    ).toBeInTheDocument();
  });

  it("не проект Студии", async () => {
    const { probe } = setup();
    probe.mockResolvedValue(makeProbe({ relation: "not_studio_project" }));
    const user = userEvent.setup();
    mount();
    await goThroughToken(user);
    const card = await screen.findByTestId("probe-result-not_studio");
    expect(card).toHaveTextContent("Это не проект Студии");
  });

  describe.each([
    ["auth_failed", "Репозиторий не принял доступ", "Изменить доступ"],
    ["forbidden_write", "У доступа нет права записи", "Изменить доступ"],
    [
      "sso_required",
      "Нужно разрешить токен для организации",
      "Проверить ещё раз",
    ],
    [
      "not_found_or_no_access",
      "Репозиторий не найден или нет доступа",
      "Изменить адрес",
    ],
    ["offline", "Нет связи с сервером", "Проверить ещё раз"],
    ["timeout", "Сервер не ответил вовремя", "Проверить ещё раз"],
    ["tls_error", "Сертификат сервера не принят", "Изменить адрес"],
    ["rate_limited", "Слишком много запросов", "Проверить ещё раз"],
    ["ssh_unavailable", "В системе нет ssh", "Изменить адрес"],
  ])("отказ %s", (code, title, primary) => {
    it("показывает причину и главное действие", async () => {
      const { probe } = setup();
      probe.mockResolvedValue(failedProbe(code, "технические подробности"));
      const user = userEvent.setup();
      mount();
      await goThroughToken(user);
      const card = await screen.findByTestId(`probe-result-${code}`);
      expect(card).toHaveAttribute("role", "alert");
      expect(card).toHaveTextContent(title);
      const buttons = within(card).getAllByRole("button");
      expect(buttons[0]).toHaveTextContent(primary);
      // Подробности спрятаны, но доступны.
      expect(card).toHaveTextContent("технические подробности");
    });
  });

  it("отказ доступа: «Изменить доступ» возвращает к шагу доступа", async () => {
    const { probe, createCredential } = setup();
    savesCredential(createCredential, PAT);
    probe.mockResolvedValue(failedProbe("auth_failed"));
    const user = userEvent.setup();
    mount();
    await goThroughToken(user);
    const card = await screen.findByTestId("probe-result-auth_failed");
    expect(
      screen
        .getByTestId("probe-checklist")
        .querySelectorAll('li[data-state="error"]'),
    ).toHaveLength(1);
    await user.click(
      within(card).getByRole("button", { name: "Изменить доступ" }),
    );
    expect(await screen.findByTestId("credential-picker")).toBeInTheDocument();
  });

  it("сеть: «Проверить ещё раз» повторяет проверку и может закончиться успехом", async () => {
    const { probe } = setup();
    probe.mockResolvedValueOnce(failedProbe("offline"));
    const user = userEvent.setup();
    mount();
    await goThroughToken(user);
    await user.click(
      await screen.findByRole("button", { name: "Проверить ещё раз" }),
    );
    expect(
      await screen.findByTestId("probe-result-ready-empty"),
    ).toBeInTheDocument();
    expect(probe).toHaveBeenCalledTimes(2);
  });

  it("нет такой ветки: можно выбрать из существующих", async () => {
    const { probe } = setup();
    probe.mockResolvedValueOnce(
      failedProbe("branch_missing", "", { branches: ["main", "develop"] }),
    );
    const user = userEvent.setup();
    mount();
    await goThroughToken(user);
    const card = await screen.findByTestId("probe-result-branch_missing");
    await user.click(within(card).getByRole("button", { name: "develop" }));
    expect(
      await screen.findByTestId("probe-result-ready-empty"),
    ).toBeInTheDocument();
    expect(probe.mock.calls[1]?.[0].branch).toBe("develop");
  });

  it("ошибка запроса проверки (адрес отвергнут сервером) тоже показана карточкой", async () => {
    const { probe } = setup();
    probe.mockRejectedValue(
      new ApiError("Не тот адрес", "url_scheme_forbidden", 400),
    );
    const user = userEvent.setup();
    mount();
    await goThroughToken(user);
    expect(
      await screen.findByTestId("probe-result-url_scheme_forbidden"),
    ).toHaveTextContent("Такой тип адреса не поддерживается");
  });

  it("при подключении сервер может отказать: карточка остаётся, окно открыто", async () => {
    const { connect } = setup();
    connect.mockRejectedValue(
      new ApiError("Другая история", "unrelated_histories", 409, {
        can_adopt: true,
      }),
    );
    const user = userEvent.setup();
    mount();
    await goThroughToken(user);
    await user.click(
      await screen.findByRole("button", { name: "Только подключить" }),
    );
    expect(
      await screen.findByTestId("probe-result-unrelated"),
    ).toBeInTheDocument();
    expect(useSyncUiStore.getState().connectDialog).not.toBeNull();
  });

  it("profile_required при подключении возвращает к «Представься»", async () => {
    const { connect } = setup();
    connect.mockRejectedValue(
      new ApiError("Нужен автор", "profile_required", 409),
    );
    const user = userEvent.setup();
    mount();
    await goThroughToken(user);
    await user.click(
      await screen.findByRole("button", { name: "Только подключить" }),
    );
    expect(await screen.findByLabelText("Имя")).toBeInTheDocument();
  });

  it("папка на компьютере: доступ не нужен, сразу проверка без доступа", async () => {
    const { probe } = setup();
    const user = userEvent.setup();
    mount();
    await typeUrl(user, "/srv/git/paper.git");
    await user.click(next());
    await waitFor(() => {
      expect(probe).toHaveBeenCalledWith({
        url: "file:///srv/git/paper.git",
        credential_id: null,
        project_id: PROJECT_ID,
      });
    });
    expect(
      await screen.findByTestId("probe-result-ready-empty"),
    ).toBeInTheDocument();
  });

  it("ключ сервера неизвестен: открывается окно с отпечатками, после доверия проверка идёт заново", async () => {
    const { probe, createCredential } = setup();
    savesCredential(createCredential, SSH_KEY);
    const trust = vi.spyOn(gitRemoteApi, "trustHost").mockResolvedValue();
    const keys = [
      { type: "ssh-rsa", fingerprint_sha256: "SHA256:rsaRsaRsa" },
      { type: "ssh-ed25519", fingerprint_sha256: "SHA256:edEdEd" },
    ];
    probe.mockResolvedValueOnce(failedProbe("host_key_unknown", "", {}, keys));
    const user = userEvent.setup();
    mount();
    await typeUrl(user, "git@github.com:hse-team/paper.git");
    await user.click(next());
    await user.click(
      await screen.findByRole("button", { name: "Создать ключ" }),
    );
    await user.click(
      await screen.findByRole("button", {
        name: /Я добавил\(а\) ключ, проверить/,
      }),
    );
    const host = await screen.findByRole("dialog", {
      name: /Сервер github.com подключается впервые/,
    });
    expect(
      within(host).getByLabelText("Отпечаток ключа ssh-ed25519"),
    ).toHaveValue("SHA256:edEdEd");
    expect(within(host).getByLabelText("Отпечаток ключа ssh-rsa")).toHaveValue(
      "SHA256:rsaRsaRsa",
    );

    // Три секунды на то, чтобы прочитать отпечаток.
    const trustButton = within(host).getByRole("button", {
      name: /Доверять серверу/,
    });
    expect(trustButton).toBeDisabled();
    await waitFor(
      () => {
        expect(trustButton).toBeEnabled();
      },
      { timeout: 4500 },
    );
    await user.click(trustButton);
    await waitFor(() => {
      expect(trust).toHaveBeenCalledWith({
        host: "github.com",
        port: null,
        fingerprint_sha256: "SHA256:edEdEd",
      });
    });
    expect(
      await screen.findByTestId("probe-result-ready-empty"),
    ).toBeInTheDocument();
    expect(probe).toHaveBeenCalledTimes(2);
  }, 15_000);
});

describe("ConnectRemoteDialog: ход проверки и английский язык", () => {
  beforeEach(async () => {
    await resetConnectEnvironment();
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("пока проверка идёт, чек-лист живой: работает первая строка, остальные ждут", async () => {
    const { probe } = setup();
    let finish: (value: ReturnType<typeof makeProbe>) => void = () => undefined;
    probe.mockReturnValue(
      new Promise((resolve) => {
        finish = resolve;
      }),
    );
    const user = userEvent.setup();
    mount();
    await goThroughToken(user);
    const list = await screen.findByTestId("probe-checklist");
    expect(list).toHaveAttribute("aria-live", "polite");
    expect(list.querySelector('li[data-state="current"]')).toHaveTextContent(
      "Адрес доступен",
    );
    expect(list.querySelectorAll('li[data-state="upcoming"]')).toHaveLength(3);
    // Итога ещё нет, а выйти из окна можно.
    expect(screen.queryByTestId(/probe-result/)).toBeNull();
    expect(screen.getByRole("button", { name: "Отмена" })).toBeEnabled();

    finish(makeProbe({ relation: "empty", empty: true }));
    expect(
      await screen.findByTestId("probe-result-ready-empty"),
    ).toBeInTheDocument();
    expect(list.querySelectorAll('li[data-state="done"]')).toHaveLength(4);
  });

  it("ушёл назад, не дождавшись ответа: прежний ответ ничего не меняет", async () => {
    const { probe, createCredential } = setup();
    savesCredential(createCredential, PAT);
    let finish: (value: ReturnType<typeof makeProbe>) => void = () => undefined;
    probe.mockReturnValue(
      new Promise((resolve) => {
        finish = resolve;
      }),
    );
    const user = userEvent.setup();
    mount();
    await goThroughToken(user);
    await screen.findByTestId("probe-checklist");
    await user.click(screen.getByRole("button", { name: "Назад" }));
    await screen.findByTestId("credential-picker");
    finish(makeProbe({ relation: "empty", empty: true }));
    await act(async () => {
      await Promise.resolve();
    });
    expect(screen.queryByTestId("probe-result-ready-empty")).toBeNull();
    expect(screen.getByTestId("credential-picker")).toBeInTheDocument();
  });

  it("английский: тексты окна и отказов переведены", async () => {
    await i18n.changeLanguage("en");
    const { probe } = setup();
    probe.mockResolvedValue(failedProbe("auth_failed", "token revoked"));
    const user = userEvent.setup();
    mount();
    expect(
      await screen.findByRole("dialog", { name: "Connect a repository" }),
    ).toBeInTheDocument();
    await user.click(await screen.findByLabelText("Repository address"));
    await user.paste("https://github.com/hse-team/paper");
    await user.click(screen.getByRole("button", { name: "Next" }));
    await user.click(await screen.findByLabelText("Token"));
    await user.keyboard(TOKEN);
    await user.click(screen.getByRole("button", { name: "Save and check" }));
    const card = await screen.findByTestId("probe-result-auth_failed");
    expect(card).toHaveTextContent("The repository did not accept the access");
    expect(
      within(card).getByRole("button", { name: "Change access" }),
    ).toBeInTheDocument();
  });
});

describe("ConnectRemoteDialog: обновить доступ", () => {
  beforeEach(async () => {
    await resetConnectEnvironment();
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("начинается с доступа, адрес не меняется, токен заменяется у того же доступа", async () => {
    const { probe, createCredential } = setup({
      status: connectedStatus(),
      credentials: [PAT],
    });
    probe.mockResolvedValue(makeProbe());
    const update = vi
      .spyOn(gitRemoteApi, "updateCredential")
      .mockResolvedValue({ ...PAT, status: "unverified" });
    const fetchRemote = vi
      .spyOn(gitSyncApi, "fetchRemote")
      .mockResolvedValue(
        connectedStatus({ ui_state: "up_to_date", health: "ok" }),
      );
    const user = userEvent.setup();
    mount("fix_access");

    expect(
      await screen.findByRole("dialog", { name: "Обновить доступ" }),
    ).toBeInTheDocument();
    expect(await screen.findByTestId("provider-chip")).toHaveTextContent(
      "hse-team/paper",
    );
    expect(screen.queryByLabelText("Адрес репозитория")).toBeNull();
    expect(
      within(screen.getByRole("list", { name: "Шаги подключения" }))
        .getByText("Доступ")
        .closest("li"),
    ).toHaveAttribute("aria-current", "step");
    // Текущий доступ показан с итогом последней проверки.
    expect(await screen.findByText("Отклонён сервером")).toBeInTheDocument();

    await user.click(screen.getByLabelText("Новый токен"));
    await user.keyboard(TOKEN);
    await user.click(
      screen.getByRole("button", { name: "Сохранить и проверить" }),
    );
    await waitFor(() => {
      expect(update).toHaveBeenCalledWith(PAT.id, { token: TOKEN });
    });
    expect(createCredential).not.toHaveBeenCalled();

    const card = await screen.findByTestId("probe-result-ready-same");
    expect(card).toHaveTextContent("Доступ работает");
    expect(
      within(card).queryByRole("button", { name: /синхронизировать/ }),
    ).toBeNull();
    await user.click(
      within(card).getByRole("button", { name: "Сохранить доступ" }),
    );
    await waitFor(() => {
      expect(fetchRemote).toHaveBeenCalledWith(PROJECT_ID);
    });
    await waitFor(() => {
      expect(useSyncUiStore.getState().connectDialog).toBeNull();
    });
    expect(useToastStore.getState().toasts.map((t) => t.message)).toContain(
      "Доступ обновлён: репозиторий принял его.",
    );
    expect(document.body.innerHTML).not.toContain(TOKEN);
  });

  it("без запомненного доступа проект подключается заново с тем же адресом", async () => {
    const disconnect = vi
      .spyOn(gitSyncApi, "disconnectRemote")
      .mockResolvedValue();
    const { probe, connect, createCredential } = setup({
      status: connectedStatus({
        remote: { ...REMOTE, credential: null },
      }),
      credentials: [],
    });
    probe.mockResolvedValue(makeProbe());
    createCredential.mockResolvedValue({ ...PAT, status: "unverified" });
    const user = userEvent.setup();
    mount("fix_access");
    await user.click(await screen.findByLabelText("Токен"));
    await user.keyboard(TOKEN);
    await user.click(
      screen.getByRole("button", { name: "Сохранить и проверить" }),
    );
    const card = await screen.findByTestId("probe-result-ready-same");
    await user.click(
      within(card).getByRole("button", { name: "Сохранить доступ" }),
    );
    await waitFor(() => {
      expect(disconnect).toHaveBeenCalledWith(PROJECT_ID, false);
    });
    await waitFor(() => {
      expect(connect).toHaveBeenCalledWith(PROJECT_ID, {
        url: "https://github.com/hse-team/paper",
        credential_id: PAT.id,
        remote_branch: "main",
      });
    });
  });

  it("открытый http: доступ обновляется у подключения, которое уже живёт на нём, и флаг не теряется", async () => {
    const disconnect = vi
      .spyOn(gitSyncApi, "disconnectRemote")
      .mockResolvedValue();
    const { probe, connect, createCredential } = setup({
      status: connectedStatus({
        remote: {
          ...REMOTE,
          display_url: "http://git.lan:8080/team/paper.git",
          kind: "http",
          host: "git.lan",
          provider: "other",
          web_url: null,
          credential: null,
          insecure_http: true,
        },
      }),
      credentials: [],
    });
    probe.mockResolvedValue(makeProbe());
    createCredential.mockResolvedValue({ ...PAT, status: "unverified" });
    const user = userEvent.setup();
    mount("fix_access");

    // Раньше адрес с http не разбирался, и шаг «Доступ» оставался пустым.
    await user.click(await screen.findByLabelText("Токен"));
    await user.keyboard(TOKEN);
    await user.click(
      screen.getByRole("button", { name: "Сохранить и проверить" }),
    );
    const card = await screen.findByTestId("probe-result-ready-same");
    // Проверка адреса тоже несёт согласие: без него сервер откажет в открытом http.
    expect(probe).toHaveBeenCalledWith(
      expect.objectContaining({ insecure_http: true }),
    );
    await user.click(
      within(card).getByRole("button", { name: "Сохранить доступ" }),
    );
    await waitFor(() => {
      expect(disconnect).toHaveBeenCalledWith(PROJECT_ID, false);
    });
    await waitFor(() => {
      expect(connect).toHaveBeenCalledWith(PROJECT_ID, {
        url: "http://git.lan:8080/team/paper.git",
        credential_id: PAT.id,
        remote_branch: "main",
        insecure_http: true,
      });
    });
  });

  it("замена доступа оборвалась: прежний доступ возвращается, окно остаётся «обновить доступ»", async () => {
    const disconnect = vi
      .spyOn(gitSyncApi, "disconnectRemote")
      .mockImplementation(() => {
        // Пока проект без репозитория, состояние отвечает «не подключён».
        vi.mocked(gitSyncApi.getStatus).mockResolvedValue(noRemoteStatus());
        return Promise.resolve();
      });
    const { probe, connect, createCredential } = setup({
      status: connectedStatus({
        remote: { ...REMOTE, credential: null },
      }),
      credentials: [],
    });
    probe.mockResolvedValue(makeProbe());
    createCredential.mockResolvedValue({ ...PAT, status: "unverified" });
    connect.mockRejectedValueOnce(
      new ApiError("Сервер недоступен", "offline", 502),
    );
    const user = userEvent.setup();
    mount("fix_access");
    await user.click(await screen.findByLabelText("Токен"));
    await user.keyboard(TOKEN);
    await user.click(
      screen.getByRole("button", { name: "Сохранить и проверить" }),
    );
    const card = await screen.findByTestId("probe-result-ready-same");
    await user.click(
      within(card).getByRole("button", { name: "Сохранить доступ" }),
    );
    await waitFor(() => {
      expect(connect).toHaveBeenCalledTimes(2);
    });
    expect(disconnect).toHaveBeenCalledTimes(1);
    // Вторая попытка: прежний адрес, ветка и прежний (пустой) доступ.
    expect(connect.mock.calls[1]?.[1]).toEqual({
      url: REMOTE.display_url,
      credential_id: null,
      remote_branch: REMOTE.branch,
    });
    expect(
      screen.getByRole("dialog", { name: "Обновить доступ" }),
    ).toBeInTheDocument();
    expect(screen.queryByLabelText("Адрес репозитория")).toBeNull();
  });
});

// --- проверка токена по вставке, типы серверов, сертификаты -------------------------

const GL_PROVIDER = { id: "gitlab", detected_by: "host", version: "17.3.1" };
const GL_CHECK = (
  over: Partial<GitCredentialCheck> = {},
): GitCredentialCheck => ({
  credential: GL_PAT,
  provider_info: GL_PROVIDER,
  token_info: {
    login: "anna.petrova",
    scopes: ["read_repository", "write_repository"],
    expires_at: null,
    sufficiency: "sufficient",
    missing: [],
  },
  ...over,
});
const GL_PAT: typeof PAT = {
  ...PAT,
  id: "cred-gl",
  label: "GitLab, gitlab.com",
  host: "gitlab.com",
  token_family: "glpat",
  status: "unverified",
};
const GL_URL = "https://gitlab.com/hse-team/paper";

const toTokenStep = async (
  user: ReturnType<typeof userEvent.setup>,
  url = GL_URL,
) => {
  await typeUrl(user, url);
  await user.click(next());
  await screen.findByLabelText("Токен");
};

describe("ConnectRemoteDialog: токен проверяется сразу после вставки", () => {
  beforeEach(async () => {
    await resetConnectEnvironment();
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("вставка сохраняет доступ, проверяет токен и показывает владельца, права и срок", async () => {
    const { createCredential, probe } = setup();
    savesCredential(createCredential, GL_PAT);
    const check = vi
      .spyOn(gitRemoteApi, "checkCredential")
      .mockResolvedValue(GL_CHECK());
    const user = userEvent.setup();
    mount();
    await toTokenStep(user);
    // Подсказка про выпуск токена стоит прямо над полем.
    expect(screen.getByTestId("token-create-link")).toHaveTextContent(
      "Создать токен на GitLab",
    );
    await user.click(screen.getByLabelText("Токен"));
    await user.paste(TOKEN);

    expect(
      await screen.findByTestId("token-check-sufficient"),
    ).toBeInTheDocument();
    expect(createCredential).toHaveBeenCalledTimes(1);
    expect(createCredential).toHaveBeenCalledWith({
      kind: "pat",
      label: "GitLab, gitlab.com",
      host: "gitlab.com",
      token: TOKEN,
    });
    expect(check).toHaveBeenCalledWith(GL_PAT.id);
    const facts = screen.getByTestId("token-facts");
    expect(facts).toHaveTextContent("anna.petrova");
    expect(facts).toHaveTextContent("write_repository");
    expect(facts).toHaveTextContent("GitLab 17.3");
    // Токена нет ни в поле, ни в разметке; сохранённый доступ выбран.
    expect(document.body.innerHTML).not.toContain(TOKEN);
    expect(screen.queryByLabelText("Токен")).toBeNull();
    expect(screen.getByLabelText(/GitLab, gitlab.com/)).toBeChecked();

    await user.click(screen.getByRole("button", { name: "Проверить" }));
    await waitFor(() => {
      expect(probe).toHaveBeenCalledWith({
        url: GL_URL,
        credential_id: GL_PAT.id,
        project_id: PROJECT_ID,
      });
    });
  });

  it("набранный вручную токен проверяется кнопкой «Проверить токен»", async () => {
    const { createCredential } = setup();
    savesCredential(createCredential, GL_PAT);
    const check = vi
      .spyOn(gitRemoteApi, "checkCredential")
      .mockResolvedValue(GL_CHECK());
    const user = userEvent.setup();
    mount();
    await toTokenStep(user);
    const checkButton = screen.getByRole("button", { name: "Проверить токен" });
    expect(checkButton).toBeDisabled();
    await user.click(screen.getByLabelText("Токен"));
    await user.keyboard(TOKEN);
    expect(createCredential).not.toHaveBeenCalled();
    await user.click(checkButton);
    expect(
      await screen.findByTestId("token-check-sufficient"),
    ).toBeInTheDocument();
    expect(check).toHaveBeenCalledTimes(1);
  });

  it("токену не хватает прав: названо, что добавить, продолжить всё равно можно", async () => {
    const { createCredential, probe } = setup();
    savesCredential(createCredential, GL_PAT);
    vi.spyOn(gitRemoteApi, "checkCredential").mockResolvedValue(
      GL_CHECK({
        token_info: {
          login: "anna.petrova",
          scopes: ["read_repository"],
          expires_at: null,
          sufficiency: "too_narrow",
          missing: ["write_repository"],
        },
      }),
    );
    const user = userEvent.setup();
    mount();
    await toTokenStep(user);
    await user.click(screen.getByLabelText("Токен"));
    await user.paste(TOKEN);
    const card = await screen.findByTestId("token-check-too_narrow");
    expect(card).toHaveTextContent("Добавь права: write_repository");
    expect(
      within(card).getByRole("link", { name: /Создать новый токен/ }),
    ).toHaveAttribute(
      "href",
      expect.stringContaining("scopes=read_repository"),
    );
    await user.click(screen.getByRole("button", { name: "Проверить" }));
    await waitFor(() => {
      expect(probe).toHaveBeenCalled();
    });
  });

  it("слишком широкий и непроверяемый токены: предупреждение и пояснение, не ошибка", async () => {
    const { createCredential } = setup();
    savesCredential(createCredential, GL_PAT);
    const check = vi.spyOn(gitRemoteApi, "checkCredential").mockResolvedValue(
      GL_CHECK({
        token_info: {
          login: "anna",
          scopes: ["api"],
          expires_at: null,
          sufficiency: "too_broad",
          missing: [],
        },
      }),
    );
    const user = userEvent.setup();
    mount();
    await toTokenStep(user);
    await user.click(screen.getByLabelText("Токен"));
    await user.paste(TOKEN);
    expect(
      await screen.findByTestId("token-check-too_broad"),
    ).toHaveTextContent("Лишние права: api");
    check.mockResolvedValue(
      GL_CHECK({
        token_info: {
          login: null,
          scopes: [],
          expires_at: null,
          sufficiency: "unknown",
          missing: [],
        },
      }),
    );
    await user.click(screen.getByRole("button", { name: "Проверить ещё раз" }));
    expect(await screen.findByTestId("token-check-unknown")).toHaveAttribute(
      "data-tone",
      "info",
    );
  });

  it("срок токена истёк: проверка говорит об этом и даёт ссылку на новый токен", async () => {
    const { createCredential } = setup();
    savesCredential(createCredential, GL_PAT);
    // Истёкший токен приходит ошибкой с кодом; срок берётся из доступа.
    vi.spyOn(gitRemoteApi, "checkCredential").mockRejectedValue(
      new ApiError("d", "token_expired", 502),
    );
    const user = userEvent.setup();
    mount();
    await toTokenStep(user);
    await user.click(screen.getByLabelText("Токен"));
    await user.paste(TOKEN);
    const card = await screen.findByTestId("token-check-expired");
    expect(card).toHaveTextContent("Срок токена истёк");
    expect(
      within(card).getByRole("link", { name: /Создать новый токен/ }),
    ).toBeInTheDocument();
  });

  it("сертификат сервера: из проверки токена открывается окно, после доверия проверка повторяется", async () => {
    const { createCredential } = setup();
    savesCredential(createCredential, GL_PAT);
    const check = vi
      .spyOn(gitRemoteApi, "checkCredential")
      .mockRejectedValueOnce(
        new ApiError("d", "tls_untrusted_ca", 502, {
          certificate: {
            fingerprint_sha256: "SHA256:abc",
            subject: "CN=gitlab.com",
            issuer: "CN=HSE Internal CA",
            not_before: "2026-01-10T00:00:00Z",
            not_after: "2027-01-10T00:00:00Z",
            self_signed: false,
          },
        }),
      );
    const update = vi
      .spyOn(gitRemoteApi, "updateHostSettings")
      .mockResolvedValue({
        host: "gitlab.com",
        port: null,
        provider_override: null,
        provider_info: GL_PROVIDER,
        ca_present: false,
        pinned_fingerprint: "SHA256:abc",
      });
    const user = userEvent.setup();
    mount();
    await toTokenStep(user);
    await user.click(screen.getByLabelText("Токен"));
    await user.paste(TOKEN);
    await user.click(
      await screen.findByRole("button", { name: "Проверить сертификат" }),
    );
    await user.click(
      await screen.findByRole("button", {
        name: "Закрепить сертификат сервера",
      }),
    );
    await user.click(screen.getByTestId("tls-pin-confirm"));
    await user.click(screen.getByTestId("tls-submit"));
    await waitFor(() => {
      expect(update).toHaveBeenCalledWith({
        host: "gitlab.com",
        port: null,
        pinned_fingerprint: "SHA256:abc",
      });
    });
    expect(
      await screen.findByTestId("token-check-sufficient"),
    ).toBeInTheDocument();
    expect(check).toHaveBeenCalledTimes(2);
  });

  it("если окно закрыли, не взяв доступ в работу, вставленный токен убирается", async () => {
    const { createCredential } = setup();
    savesCredential(createCredential, GL_PAT);
    vi.spyOn(gitRemoteApi, "checkCredential").mockResolvedValue(GL_CHECK());
    const remove = vi
      .spyOn(gitRemoteApi, "deleteCredential")
      .mockResolvedValue(undefined);
    const user = userEvent.setup();
    mount();
    await toTokenStep(user);
    await user.click(screen.getByLabelText("Токен"));
    await user.paste(TOKEN);
    await screen.findByTestId("token-check-sufficient");
    expect(remove).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Назад" }));
    await waitFor(() => {
      expect(remove).toHaveBeenCalledWith(GL_PAT.id);
    });
  });

  it("взятый в работу доступ не убирается", async () => {
    const { createCredential } = setup();
    savesCredential(createCredential, GL_PAT);
    vi.spyOn(gitRemoteApi, "checkCredential").mockResolvedValue(GL_CHECK());
    const remove = vi
      .spyOn(gitRemoteApi, "deleteCredential")
      .mockResolvedValue(undefined);
    const user = userEvent.setup();
    mount();
    await toTokenStep(user);
    await user.click(screen.getByLabelText("Токен"));
    await user.paste(TOKEN);
    await screen.findByTestId("token-check-sufficient");
    await user.click(screen.getByRole("button", { name: "Проверить" }));
    await screen.findByTestId("probe-checklist");
    await user.click(screen.getByRole("button", { name: "Отмена" }));
    expect(remove).not.toHaveBeenCalled();
  });

  it("обновление доступа: вставка заменяет токен у привязанного доступа и проверяется", async () => {
    const { probe } = setup({
      status: connectedStatus(),
      credentials: [PAT],
    });
    probe.mockResolvedValue(makeProbe());
    const update = vi
      .spyOn(gitRemoteApi, "updateCredential")
      .mockResolvedValue({ ...PAT, status: "unverified" });
    const check = vi
      .spyOn(gitRemoteApi, "checkCredential")
      .mockResolvedValue(CHECK_OK);
    vi.spyOn(gitSyncApi, "fetchRemote").mockResolvedValue(
      connectedStatus({ ui_state: "up_to_date", health: "ok" }),
    );
    const user = userEvent.setup();
    mount("fix_access");
    await user.click(await screen.findByLabelText("Новый токен"));
    await user.paste(TOKEN);
    expect(
      await screen.findByTestId("token-check-sufficient"),
    ).toBeInTheDocument();
    expect(update).toHaveBeenCalledWith(PAT.id, { token: TOKEN });
    expect(check).toHaveBeenCalledWith(PAT.id);
    // Токен заменён: кнопка идёт дальше без повторной вставки.
    await user.click(screen.getByRole("button", { name: "Проверить" }));
    expect(
      await screen.findByTestId("probe-result-ready-same"),
    ).toBeInTheDocument();
    expect(update).toHaveBeenCalledTimes(1);
  });
});

describe("ConnectRemoteDialog: тип сервера и ответы проверки адреса", () => {
  beforeEach(async () => {
    await resetConnectEnvironment();
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("выбранный человеком тип сервера меняет ссылку на токен", async () => {
    setup();
    const update = vi
      .spyOn(gitRemoteApi, "updateHostSettings")
      .mockResolvedValue({
        host: "git.corp.example",
        port: null,
        provider_override: "gitlab",
        provider_info: { id: "gitlab", detected_by: "override", version: null },
        ca_present: false,
        pinned_fingerprint: null,
      });
    const user = userEvent.setup();
    mount();
    await typeUrl(user, "https://git.corp.example/team/paper");
    expect(screen.getByTestId("provider-chip")).toHaveTextContent(
      "Другой сервер",
    );
    // Выбор типа запоминается, список настроек после этого приходит уже с ним.
    vi.mocked(gitRemoteApi.listHostSettings).mockResolvedValue([
      {
        host: "git.corp.example",
        port: null,
        provider_override: "gitlab",
        provider_info: { id: "gitlab", detected_by: "override", version: null },
        ca_present: false,
        pinned_fingerprint: null,
      },
    ]);
    await user.click(screen.getByTestId("provider-change"));
    await user.click(await screen.findByTestId("provider-option-gitlab"));
    await waitFor(() => {
      expect(update).toHaveBeenCalled();
    });
    await waitFor(() => {
      expect(screen.getByTestId("provider-chip")).toHaveTextContent("GitLab");
    });
    await user.click(next());
    expect(await screen.findByTestId("token-create-link")).toHaveTextContent(
      "Создать токен на GitLab",
    );
    expect(
      new URL(
        screen.getByTestId("token-create-link").getAttribute("href") ?? "",
      ).host,
    ).toBe("git.corp.example");
  });

  it("версия сервера из ответа проверки видна в итоге", async () => {
    const { probe, createCredential } = setup();
    savesCredential(createCredential, GL_PAT);
    probe.mockResolvedValue(
      makeProbe({
        relation: "empty",
        empty: true,
        provider_info: GL_PROVIDER,
        token_info: {
          login: "anna.petrova",
          scopes: ["read_repository"],
          expires_at: new Date(Date.now() + 3 * 24 * 3600 * 1000).toISOString(),
          sufficiency: "too_narrow",
          missing: ["write_repository"],
        },
      }),
    );
    const user = userEvent.setup();
    mount();
    await toTokenStep(user);
    await user.click(screen.getByLabelText("Токен"));
    await user.keyboard(TOKEN);
    await user.click(
      screen.getByRole("button", { name: "Сохранить и проверить" }),
    );
    const card = await screen.findByTestId("probe-result-ready-empty");
    expect(card).toHaveTextContent("GitLab 17.3");
    expect(card).toHaveTextContent("anna.petrova");
    expect(card).toHaveTextContent("добавь write_repository");
    expect(card).toHaveTextContent("перестанет действовать через 3 дня");
  });

  it("сертификат внутреннего сервера: окно открывается само, после доверия проверка идёт заново", async () => {
    const { probe } = setup({
      credentials: [{ ...GL_PAT, host: "gitlab.hse.local" }],
    });
    const certificate = {
      fingerprint_sha256: "SHA256:b1Kq0vU7m4Zl9Xc2Tn8RjHf3eWyAo5DsPi6GgLxEu0w",
      subject: "CN=gitlab.hse.local",
      issuer: "CN=HSE Internal CA",
      not_before: "2026-01-10T00:00:00Z",
      not_after: "2027-01-10T00:00:00Z",
      self_signed: false,
    };
    probe.mockResolvedValueOnce(
      failedProbe("tls_untrusted_ca", "d", {
        reachable: false,
        error: { code: "tls_untrusted_ca", detail: "d", certificate },
      }),
    );
    probe.mockResolvedValue(makeProbe({ relation: "empty", empty: true }));
    const update = vi
      .spyOn(gitRemoteApi, "updateHostSettings")
      .mockResolvedValue({
        host: "gitlab.hse.local",
        port: null,
        provider_override: null,
        provider_info: GL_PROVIDER,
        ca_present: true,
        pinned_fingerprint: null,
      });
    const user = userEvent.setup();
    mount();
    await typeUrl(user, "https://gitlab.hse.local/team/paper");
    await user.click(next());
    await user.click(await screen.findByLabelText(/GitLab, gitlab.com/));
    await user.click(screen.getByRole("button", { name: "Проверить" }));

    const dialog = await screen.findByRole("dialog", {
      name: /Сертификат gitlab.hse.local не из известного центра/,
    });
    // За окном видна карточка отказа с данными сертификата.
    expect(
      screen.getByTestId("probe-result-tls_untrusted_ca"),
    ).toHaveTextContent("CN=HSE Internal CA");
    await user.click(within(dialog).getByTestId("tls-ca-text"));
    await user.paste(PEM_TEXT);
    await user.click(within(dialog).getByTestId("tls-submit"));
    await waitFor(() => {
      expect(update).toHaveBeenCalledWith({
        host: "gitlab.hse.local",
        port: null,
        ca_pem: PEM_TEXT,
      });
    });
    expect(
      await screen.findByTestId("probe-result-ready-empty"),
    ).toBeInTheDocument();
    expect(probe).toHaveBeenCalledTimes(2);
  });

  it("токен просрочен: отказ разобран и ведёт к доступу", async () => {
    const { probe } = setup({ credentials: [GL_PAT] });
    probe.mockResolvedValueOnce(
      failedProbe("token_expired", "Срок действия токена истёк."),
    );
    const user = userEvent.setup();
    mount();
    await typeUrl(user, GL_URL);
    await user.click(next());
    await user.click(await screen.findByLabelText(/GitLab, gitlab.com/));
    await user.click(screen.getByRole("button", { name: "Проверить" }));
    const expired = await screen.findByTestId("probe-result-token_expired");
    expect(expired).toHaveTextContent("Срок токена истёк");
    await user.click(
      within(expired).getByRole("button", { name: "Изменить доступ" }),
    );
    expect(await screen.findByTestId("credential-picker")).toBeInTheDocument();
    expect(screen.queryByTestId("probe-result-token_expired")).toBeNull();
  });

  it("срок сохранённого токена виден в списке доступов", async () => {
    setup({
      credentials: [
        {
          ...GL_PAT,
          status: "ok",
          expires_at: new Date(Date.now() + 5 * 24 * 3600 * 1000).toISOString(),
        },
      ],
    });
    const user = userEvent.setup();
    mount();
    await typeUrl(user, GL_URL);
    await user.click(next());
    expect(await screen.findByTestId("expiry-badge")).toHaveTextContent(
      "Истекает через 5 дней",
    );
  });
});

const PEM_TEXT =
  "-----BEGIN CERTIFICATE-----\nMIIBdemo\n-----END CERTIFICATE-----";

const DEPLOY_KEY = {
  ...SSH_KEY,
  id: "cred-deploy",
  label: "Deploy-ключ: hse-team/paper",
};

describe("ConnectRemoteDialog: способы доступа вкладками", () => {
  beforeEach(async () => {
    await resetConnectEnvironment();
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  const openAccess = async (
    user: ReturnType<typeof userEvent.setup>,
    url = "https://github.com/hse-team/paper",
  ) => {
    await typeUrl(user, url);
    await user.click(next());
    return screen.findByTestId("access-tabs");
  };

  it("предлагает токен, ключ, deploy-ключ и публичный репозиторий; по умолчанию токен", async () => {
    setup();
    const user = userEvent.setup();
    mount();
    const tabs = await openAccess(user);
    const names = within(tabs)
      .getAllByRole("tab")
      .map((tab) => tab.id.split("-tab-")[1]);
    expect(names).toEqual(["pat", "ssh", "deploy", "none"]);
    expect(
      within(tabs).getByRole("tab", {
        name: /Токен \(HTTPS\)/,
        selected: true,
      }),
    ).toBeInTheDocument();
    // Панель связана с выбранной вкладкой.
    const panel = screen.getByRole("tabpanel");
    expect(panel).toHaveAttribute(
      "aria-labelledby",
      within(tabs).getByRole("tab", { selected: true }).id,
    );
    expect(within(panel).getByTestId("pat-panel")).toBeInTheDocument();
  });

  it("стрелки переключают вкладки по кругу", async () => {
    setup();
    const user = userEvent.setup();
    mount();
    const tabs = await openAccess(user);
    within(tabs).getByRole("tab", { selected: true }).focus();
    await user.keyboard("{ArrowRight}");
    expect(
      within(tabs).getByRole("tab", { name: /Ключ Студии/, selected: true }),
    ).toHaveFocus();
    await user.keyboard("{ArrowLeft}");
    expect(
      within(tabs).getByRole("tab", {
        name: /Токен \(HTTPS\)/,
        selected: true,
      }),
    ).toHaveFocus();
    await user.keyboard("{ArrowLeft}");
    expect(
      within(tabs).getByRole("tab", {
        name: /Публичный репозиторий/,
        selected: true,
      }),
    ).toHaveFocus();
    await user.keyboard("{Home}");
    expect(
      within(tabs).getByRole("tab", {
        name: /Токен \(HTTPS\)/,
        selected: true,
      }),
    ).toHaveFocus();
  });

  it("deploy-ключ: создаётся для репозитория, ссылка ведёт на его страницу, ключ в поле копирования", async () => {
    const { createCredential } = setup();
    savesCredential(createCredential, DEPLOY_KEY);
    const user = userEvent.setup();
    mount();
    const tabs = await openAccess(user);
    await user.click(within(tabs).getByRole("tab", { name: /Deploy-ключ/ }));
    expect(await screen.findByTestId("deploy-repo")).toHaveTextContent(
      "hse-team/paper",
    );
    expect(
      screen.getByText("Deploy-ключа для hse-team/paper ещё нет"),
    ).toBeInTheDocument();
    await user.click(
      screen.getByRole("button", { name: "Создать deploy-ключ" }),
    );
    await waitFor(() => {
      expect(createCredential).toHaveBeenCalledWith({
        kind: "ssh_key",
        label: "Deploy-ключ: hse-team/paper",
        host: "github.com",
      });
    });
    expect(
      await screen.findByLabelText("Публичный ключ", { selector: "textarea" }),
    ).toHaveValue(DEPLOY_KEY.public_key);
    expect(
      screen.getByRole("link", {
        name: /Открыть страницу deploy-ключей GitHub/,
      }),
    ).toHaveAttribute(
      "href",
      "https://github.com/hse-team/paper/settings/keys/new",
    );
    // Запись разрешают отдельно: без неё отправить версии не получится.
    expect(screen.getAllByText(/Allow write access/).length).toBeGreaterThan(0);
    await user.click(
      screen.getByRole("button", { name: "Я добавил(а) ключ, проверить" }),
    );
    await waitFor(() => {
      expect(vi.mocked(gitRemoteApi.probe)).toHaveBeenCalledWith({
        url: "https://github.com/hse-team/paper",
        credential_id: DEPLOY_KEY.id,
        project_id: PROJECT_ID,
      });
    });
  });

  it("ключи пользователя и deploy-ключи не смешиваются, чужой репозиторий не подходит", async () => {
    setup({
      credentials: [
        SSH_KEY,
        DEPLOY_KEY,
        {
          ...DEPLOY_KEY,
          id: "cred-other",
          label: "Deploy-ключ: hse-team/other",
        },
      ],
    });
    const user = userEvent.setup();
    mount();
    const tabs = await openAccess(user);
    await user.click(within(tabs).getByRole("tab", { name: /Ключ Студии/ }));
    const userPanel = await screen.findByTestId("ssh-panel");
    expect(userPanel).toHaveAttribute("data-scope", "user");
    expect(within(userPanel).queryByText(/Deploy-ключ/)).toBeNull();
    expect(
      within(userPanel).getByLabelText("Публичный ключ", {
        selector: "textarea",
      }),
    ).toBeInTheDocument();

    await user.click(within(tabs).getByRole("tab", { name: /Deploy-ключ/ }));
    const deployPanel = await screen.findByTestId("ssh-panel");
    expect(deployPanel).toHaveAttribute("data-scope", "deploy");
    // Нашёлся ровно один ключ этого репозитория, выбор не нужен.
    expect(within(deployPanel).queryByRole("radiogroup")).toBeNull();
    expect(
      within(deployPanel).getByLabelText("Публичный ключ", {
        selector: "textarea",
      }),
    ).toBeInTheDocument();
  });

  it("у провайдера без deploy-ключей такой вкладки нет", async () => {
    setup();
    const user = userEvent.setup();
    mount();
    const tabs = await openAccess(
      user,
      "https://git.example.org/team/paper.git",
    );
    expect(within(tabs).queryByRole("tab", { name: /Deploy-ключ/ })).toBeNull();
    expect(within(tabs).getAllByRole("tab")).toHaveLength(3);
  });

  it("публичный репозиторий: без токена, проверка идёт без доступа и говорит про чтение", async () => {
    const { probe, connect } = setup();
    const user = userEvent.setup();
    mount();
    const tabs = await openAccess(user);
    await user.click(
      within(tabs).getByRole("tab", { name: /Публичный репозиторий/ }),
    );
    const panel = await screen.findByTestId("public-panel");
    expect(panel).toHaveTextContent("Получать версии из репозитория");
    expect(panel).toHaveTextContent("Отправлять свои версии нельзя");
    expect(screen.queryByTestId("pat-panel")).toBeNull();
    await user.click(screen.getByRole("button", { name: "Проверить" }));
    await waitFor(() => {
      expect(probe).toHaveBeenCalledWith({
        url: "https://github.com/hse-team/paper",
        credential_id: null,
        project_id: PROJECT_ID,
      });
    });
    expect(
      await screen.findByText(/версии будут только приходить/),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Только подключить" }));
    await waitFor(() => {
      expect(connect).toHaveBeenCalledWith(PROJECT_ID, {
        url: "https://github.com/hse-team/paper",
        credential_id: null,
      });
    });
  });

  it("вернулся с публичного на токен, проверка берёт токен, а не «без доступа»", async () => {
    const { probe } = setup({ credentials: [{ ...PAT, status: "ok" }] });
    const user = userEvent.setup();
    mount();
    const tabs = await openAccess(user);
    await user.click(
      within(tabs).getByRole("tab", { name: /Публичный репозиторий/ }),
    );
    await user.click(screen.getByRole("button", { name: "Проверить" }));
    await screen.findByText(/версии будут только приходить/);
    await user.click(screen.getByRole("button", { name: "Назад" }));
    await user.click(
      await screen.findByRole("tab", { name: /Токен \(HTTPS\)/ }),
    );
    await user.click(screen.getByRole("button", { name: "Проверить" }));
    await waitFor(() => {
      expect(probe).toHaveBeenLastCalledWith(
        expect.objectContaining({ credential_id: PAT.id }),
      );
    });
  });

  it("при обновлении доступа вкладок нет: меняется только токен или ключ", async () => {
    setup({
      status: connectedStatus(),
      credentials: [{ ...PAT, status: "auth_failed" }],
    });
    const user = userEvent.setup();
    mount("fix_access");
    await screen.findByTestId("pat-panel");
    expect(user).toBeDefined();
    expect(screen.queryByTestId("access-tabs")).toBeNull();
  });
});
