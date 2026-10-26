import { act, cleanup, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@shared/api";
import { useToastStore } from "@shared/lib";
import { i18n } from "@shared/lib/i18n";
import { gitRemoteApi } from "@entities/git-remote";
import { gitSyncApi, useSyncUiStore } from "@entities/git-sync";
import { profileApi } from "@entities/profile";
import {
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
  await user.paste(TOKEN);
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
    await user.paste(TOKEN);
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
    await user.paste(TOKEN);
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
    await user.paste(TOKEN);
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
    // Для ssh-адреса сразу открыт способ «ключ».
    expect(
      await screen.findByRole("button", { name: "Ключ (ssh)", pressed: true }),
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
    expect(screen.getAllByText(/Allow write access/).length).toBeGreaterThan(0);
    // Прямая ссылка на страницу ключей репозитория.
    expect(
      screen.getByRole("link", { name: /Открыть страницу ключей GitHub/ }),
    ).toHaveAttribute(
      "href",
      "https://github.com/hse-team/paper/settings/keys/new",
    );

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
      await screen.findByRole("button", { name: "Токен (https)" }),
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

  it("вход через браузер виден, но выключен", async () => {
    setup();
    const user = userEvent.setup();
    mount();
    await typeUrl(user, "https://github.com/hse-team/paper");
    await user.click(next());
    const card = await screen.findByTestId("browser-login-card");
    expect(card).toHaveAttribute("aria-disabled", "true");
    expect(card).toHaveTextContent("Скоро");
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
    await user.paste(TOKEN);
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
    await user.paste(TOKEN);
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
    await user.paste(TOKEN);
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
    await user.paste(TOKEN);
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
    await user.paste(TOKEN);
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
    await user.paste(TOKEN);
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
