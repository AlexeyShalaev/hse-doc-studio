import { act, cleanup, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@shared/api";
import { gitRemoteApi } from "@entities/git-remote";
import { gitSyncApi, type GitOperation } from "@entities/git-sync";
import { profileApi } from "@entities/profile";
import {
  CHECK_OK,
  CUSTOM_PROFILE,
  DEFAULT_PROFILE,
  PAT,
  failedProbe,
  makeProbe,
} from "../../testing/connectFixtures";
import {
  renderWithClient,
  resetConnectEnvironment,
} from "../../testing/renderConnect";
import {
  CloneWizard,
  type CloneFolderSlot,
  type CloneWizardProps,
} from "./CloneWizard";

const OP_ID = "op_7f3a9c21";
const NEW_PROJECT_ID = "5f0c2b7e-3b1a-4d6e-9a54-0a1b2c3d4e5f";
const DEFAULT_FOLDER = "/Users/anna/HSE Doc Studio/Курсовая работа";
const URL_TEXT = "https://github.com/hse-team/paper";

const operation = (overrides: Partial<GitOperation> = {}): GitOperation => ({
  id: OP_ID,
  kind: "clone",
  project_id: null,
  status: "running",
  phase: "download",
  percent: 55,
  message: "Получение объектов",
  cancellable: true,
  started_at: "2026-10-26T09:29:12Z",
  finished_at: null,
  result: null,
  error: null,
  ...overrides,
});

const succeeded = (
  result: Partial<{
    access: string;
    required_studio: string | null;
    warnings: { code: string; paths: string[] }[];
  }> = {},
): GitOperation =>
  operation({
    status: "succeeded",
    phase: "register",
    percent: 100,
    cancellable: false,
    project_id: NEW_PROJECT_ID,
    finished_at: "2026-10-26T09:30:00Z",
    result: {
      project_id: NEW_PROJECT_ID,
      folder: DEFAULT_FOLDER,
      access: "full",
      required_studio: null,
      warnings: [],
      ...result,
    },
  });

type Setup = {
  profile?: typeof CUSTOM_PROFILE;
  credentials?: (typeof PAT)[];
  probe?: ReturnType<typeof makeProbe>;
  operation?: GitOperation;
};

const setup = (options: Setup = {}) => {
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
  vi.spyOn(gitRemoteApi, "getSharedFolder").mockResolvedValue({
    detected: false,
    provider: null,
    root: null,
    evidence: [],
  });
  vi.spyOn(gitRemoteApi, "getCloneDefaults").mockResolvedValue({
    folder: DEFAULT_FOLDER,
  });
  const probe = vi
    .spyOn(gitRemoteApi, "probe")
    .mockResolvedValue(
      options.probe ??
        makeProbe({ relation: "studio_project", default_branch: "main" }),
    );
  const startClone = vi
    .spyOn(gitRemoteApi, "startClone")
    .mockResolvedValue({ operation_id: OP_ID });
  const startBundle = vi
    .spyOn(gitRemoteApi, "startCloneFromBundle")
    .mockResolvedValue({ operation_id: OP_ID });
  const getOperation = vi
    .spyOn(gitSyncApi, "getOperation")
    .mockResolvedValue(options.operation ?? operation());
  const cancel = vi
    .spyOn(gitSyncApi, "cancelOperation")
    .mockResolvedValue(
      operation({ status: "cancelled", cancellable: false, percent: null }),
    );
  return { probe, startClone, startBundle, getOperation, cancel };
};

// Окно выбора папки и проверка папки приходят от страницы: здесь их заменяют заглушки.
const pickerSlot = (
  inspect: CloneFolderSlot["useInspect"] = () => ({ state: "idle" }),
): CloneFolderSlot => ({
  Picker: ({ isOpen, onSelect, onClose }) =>
    isOpen ? (
      <div role="dialog" aria-label="Выбор папки">
        <button
          type="button"
          onClick={() => {
            onSelect("/Users/anna/picked");
            onClose();
          }}
        >
          Выбрать /Users/anna/picked
        </button>
      </div>
    ) : null,
  useInspect: inspect,
});

const mount = (props: Partial<CloneWizardProps> = {}) => {
  const onExit = vi.fn();
  const onOpenProject = vi.fn();
  const view = renderWithClient(
    <CloneWizard onExit={onExit} onOpenProject={onOpenProject} {...props} />,
  );
  return { ...view, onExit, onOpenProject };
};

type User = ReturnType<typeof userEvent.setup>;

const typeUrl = async (user: User, url = URL_TEXT) => {
  await user.click(
    await screen.findByRole("textbox", { name: "Адрес репозитория" }),
  );
  await user.paste(url);
};

const checkPublic = async (user: User, url = URL_TEXT) => {
  await typeUrl(user, url);
  await user.click(
    await screen.findByRole("tab", { name: /Публичный репозиторий/ }),
  );
  await user.click(
    screen.getByRole("button", { name: "Проверить репозиторий" }),
  );
};

const next = () => screen.getByRole("button", { name: "Далее" });

const toFolderStep = async (user: User, url = URL_TEXT) => {
  await checkPublic(user, url);
  await screen.findByText("Проект найден");
  await user.click(next());
  await screen.findByLabelText("Папка на компьютере");
};

const startCloning = async (user: User) => {
  await user.click(screen.getByRole("button", { name: "Клонировать" }));
};

describe("мастер клонирования: источник и проверка адреса", () => {
  beforeEach(async () => {
    await resetConnectEnvironment();
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("показывает три шага и первый шаг с адресом и способами доступа", async () => {
    setup();
    mount();
    const steps = await screen.findByRole("list", {
      name: "Шаги клонирования",
    });
    expect(within(steps).getByText("Источник")).toBeInTheDocument();
    expect(within(steps).getByText("Папка")).toBeInTheDocument();
    expect(within(steps).getByText("Загрузка")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Клонировать проект из git" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("tab", { name: "Адрес репозитория", selected: true }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("tab", { name: "Файл bundle" }),
    ).toBeInTheDocument();
    // Пока адреса нет, проверять нечего.
    expect(
      screen.getByRole("button", { name: "Проверить репозиторий" }),
    ).toBeDisabled();
    expect(screen.queryByTestId("clone-access")).toBeNull();
  });

  it("после адреса показывает способы доступа, в том числе открытый репозиторий", async () => {
    setup();
    const user = userEvent.setup();
    mount();
    await typeUrl(user);
    const access = await screen.findByTestId("clone-access");
    expect(within(access).getByLabelText("Токен")).toBeInTheDocument();
    expect(
      within(access).getByRole("tab", { name: /Публичный репозиторий/ }),
    ).toBeInTheDocument();
    await user.click(
      within(access).getByRole("tab", { name: /Публичный репозиторий/ }),
    );
    expect(
      within(access).getByText(/Токен и ключ не нужны/),
    ).toBeInTheDocument();
  });

  it("проверяет открытый репозиторий без доступа и показывает карточку проекта", async () => {
    const { probe } = setup();
    const user = userEvent.setup();
    mount();
    await checkPublic(user);

    const card = await screen.findByTestId("clone-verdict-ready-full");
    expect(probe).toHaveBeenCalledWith({
      url: "https://github.com/hse-team/paper",
      credential_id: null,
    });
    expect(within(card).getByText("Проект найден")).toBeInTheDocument();
    expect(
      within(card).getByText("github.com/hse-team/paper"),
    ).toBeInTheDocument();
    expect(within(card).getByText("Курсовая работа")).toBeInTheDocument();
    expect(
      within(card).getByText("hse-cs-sse / coursework 1.2.0"),
    ).toBeInTheDocument();
    expect(within(card).getByText(/Команда · 2 автора/)).toBeInTheDocument();
    expect(
      within(card).getByText(/Проект откроется для полной работы/),
    ).toBeInTheDocument();
    expect(next()).toBeEnabled();
  });

  it("сохраняет токен и проверяет репозиторий с созданным доступом", async () => {
    const { probe } = setup();
    const createCredential = vi
      .spyOn(gitRemoteApi, "createCredential")
      .mockResolvedValue({ ...PAT, id: "cred-new", status: "unverified" });
    const user = userEvent.setup();
    mount();
    await typeUrl(user);
    await user.click(await screen.findByLabelText("Токен"));
    await user.keyboard("github_pat_SECRET_TOKEN_VALUE_123");
    await user.click(
      screen.getByRole("button", { name: "Сохранить и проверить" }),
    );
    await screen.findByTestId("clone-verdict-ready-full");
    expect(createCredential).toHaveBeenCalledWith(
      expect.objectContaining({ kind: "pat", host: "github.com" }),
    );
    expect(probe).toHaveBeenCalledWith({
      url: "https://github.com/hse-team/paper",
      credential_id: "cred-new",
    });
    // Токен нигде не остался на странице.
    expect(
      document.body.innerHTML.includes("github_pat_SECRET_TOKEN_VALUE_123"),
    ).toBe(false);
  });

  it("предлагает сохранённый доступ к серверу и проверяет с ним", async () => {
    const { probe } = setup({
      credentials: [{ ...PAT, status: "ok" }],
    });
    const user = userEvent.setup();
    mount();
    await typeUrl(user);
    expect(await screen.findByTestId("credential-picker")).toBeInTheDocument();
    await user.click(
      screen.getByRole("button", { name: "Проверить репозиторий" }),
    );
    await screen.findByTestId("clone-verdict-ready-full");
    expect(probe).toHaveBeenCalledWith({
      url: "https://github.com/hse-team/paper",
      credential_id: "cred-pat",
    });
  });

  it("предупреждает, что проект откроется только для чтения: версия Студии и нет шаблона", async () => {
    setup({
      probe: makeProbe({
        relation: "studio_project",
        schema_access: "read_only",
        required_studio: "0.4.0",
        template_available: false,
      }),
    });
    const user = userEvent.setup();
    mount();
    await checkPublic(user);

    const card = await screen.findByTestId("clone-verdict-ready-read_only");
    const verdict = within(card).getByTestId("clone-access-verdict");
    expect(
      within(verdict).getByText(/Проект откроется только для чтения/),
    ).toBeInTheDocument();
    expect(
      within(verdict).getByText(
        /создан более новой версией Студии. Нужна версия 0.4.0/,
      ),
    ).toBeInTheDocument();
    expect(
      within(verdict).getByText(/Шаблона проекта нет в этой версии Студии/),
    ).toBeInTheDocument();
    // Клонировать можно: это предупреждение, не запрет.
    expect(next()).toBeEnabled();
  });

  it("без шаблона в этой версии Студии проект откроется на чтение", async () => {
    setup({
      probe: makeProbe({
        relation: "studio_project",
        template_available: false,
      }),
    });
    const user = userEvent.setup();
    mount();
    await checkPublic(user);
    const card = await screen.findByTestId("clone-verdict-ready-read_only");
    expect(
      within(card).getByText(/Шаблона проекта нет в этой версии Студии/),
    ).toBeInTheDocument();
  });

  it("проект только для файлов: объясняет, что документов и сборки не будет", async () => {
    setup({
      probe: makeProbe({
        relation: "studio_project",
        schema_access: "files_only",
        required_studio: "1.0.0",
      }),
    });
    const user = userEvent.setup();
    mount();
    await checkPublic(user);
    const card = await screen.findByTestId("clone-verdict-ready-files_only");
    expect(
      within(card).getByText(/документы и сборка недоступны/),
    ).toBeInTheDocument();
  });

  it("репозиторий не от Студии: блокирует переход дальше", async () => {
    setup({
      probe: makeProbe({
        relation: "not_studio_project",
        project: null,
        schema_access: null,
        template_available: null,
      }),
    });
    const user = userEvent.setup();
    mount();
    await checkPublic(user);
    const card = await screen.findByTestId("clone-verdict-not_studio");
    expect(
      within(card).getByText("В репозитории нет проекта Студии"),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Далее" })).not.toBeNull();
    expect(next()).toBeDisabled();
    await user.click(
      within(card).getByRole("button", { name: "Выбрать другой репозиторий" }),
    );
    // Возвращаемся к адресу и доступу.
    expect(await screen.findByTestId("clone-access")).toBeInTheDocument();
  });

  it("пустой репозиторий: клонировать нечего", async () => {
    setup({
      probe: makeProbe({
        relation: "empty",
        empty: true,
        project: null,
        default_branch: null,
        branches: [],
        schema_access: null,
        template_available: null,
      }),
    });
    const user = userEvent.setup();
    mount();
    await checkPublic(user);
    const card = await screen.findByTestId("clone-verdict-empty");
    expect(within(card).getByText("Репозиторий пуст")).toBeInTheDocument();
    expect(next()).toBeDisabled();
  });

  it("отказ в доступе объясняет причину и возвращает к доступу", async () => {
    setup({ probe: failedProbe("auth_failed", "Сервер отклонил токен") });
    const user = userEvent.setup();
    mount();
    await checkPublic(user);
    const card = await screen.findByTestId("probe-result-auth_failed");
    expect(card).toBeInTheDocument();
    await user.click(
      within(card).getByRole("button", {
        name: /Изменить доступ|Вернуться к доступу/,
      }),
    );
    expect(await screen.findByTestId("clone-access")).toBeInTheDocument();
  });

  it("ключ сервера незнакомый: сразу открывает окно подтверждения", async () => {
    setup({
      probe: failedProbe("host_key_unknown", "", {}, [
        {
          type: "ssh-ed25519",
          fingerprint_sha256:
            "SHA256:+DiY3wvvV6TuJJhbpZisF/zLDA0zPMSvHdkr4UvCOqU",
        },
      ]),
    });
    const user = userEvent.setup();
    mount();
    await typeUrl(user, "git@github.com:hse-team/paper.git");
    await user.click(
      await screen.findByRole("tab", { name: /Публичный репозиторий/ }),
    );
    await user.click(
      screen.getByRole("button", { name: "Проверить репозиторий" }),
    );
    expect(
      await screen.findByRole("dialog", {
        name: /Сервер github.com подключается впервые/,
      }),
    ).toBeInTheDocument();
  });

  it("сертификат внутреннего сервера: окно открывается само, после доверия проверка идёт заново", async () => {
    const certificate = {
      fingerprint_sha256: "SHA256:b1Kq0vU7m4Zl9Xc2Tn8RjHf3eWyAo5DsPi6GgLxEu0w",
      subject: "CN=gitlab.hse.local",
      issuer: "CN=HSE Internal CA",
      not_before: "2026-01-10T00:00:00Z",
      not_after: "2027-01-10T00:00:00Z",
      self_signed: false,
    };
    const { probe } = setup();
    probe.mockResolvedValueOnce(
      failedProbe("tls_untrusted_ca", "", {
        error: { code: "tls_untrusted_ca", detail: "", certificate },
      }),
    );
    const update = vi
      .spyOn(gitRemoteApi, "updateHostSettings")
      .mockResolvedValue({
        host: "gitlab.hse.local",
        port: null,
        provider_override: null,
        provider_info: { id: "gitlab", detected_by: "host", version: null },
        ca_present: false,
        pinned_fingerprint: certificate.fingerprint_sha256,
      });
    const user = userEvent.setup();
    mount();
    await typeUrl(user, "https://gitlab.hse.local/team/paper.git");
    await user.click(
      await screen.findByRole("tab", { name: /Публичный репозиторий/ }),
    );
    await user.click(
      screen.getByRole("button", { name: "Проверить репозиторий" }),
    );
    expect(
      await screen.findByRole("dialog", {
        name: /Сертификат gitlab.hse.local не из известного центра/,
      }),
    ).toBeInTheDocument();
    await user.click(
      screen.getByRole("button", { name: "Закрепить сертификат сервера" }),
    );
    await user.click(screen.getByTestId("tls-pin-confirm"));
    await user.click(screen.getByTestId("tls-submit"));
    await waitFor(() => {
      expect(update).toHaveBeenCalledWith({
        host: "gitlab.hse.local",
        port: null,
        pinned_fingerprint: certificate.fingerprint_sha256,
      });
    });
    await waitFor(() => {
      expect(probe).toHaveBeenCalledTimes(2);
    });
  });

  it("ветка из списка запускает проверку заново с этой веткой", async () => {
    const { probe } = setup({
      probe: makeProbe({
        relation: "studio_project",
        default_branch: "main",
        branches: ["main", "develop"],
      }),
    });
    const user = userEvent.setup();
    mount();
    await checkPublic(user);
    const card = await screen.findByTestId("clone-verdict-ready-full");
    expect(
      within(card).getByRole("button", { name: /main/, pressed: true }),
    ).toBeInTheDocument();
    await user.click(within(card).getByRole("button", { name: "develop" }));
    await waitFor(() => {
      expect(probe).toHaveBeenLastCalledWith({
        url: "https://github.com/hse-team/paper",
        credential_id: null,
        branch: "develop",
      });
    });
    expect(
      await screen.findByRole("button", { name: "develop", pressed: true }),
    ).toBeInTheDocument();
  });

  it("токен из вставленного адреса убирается и не уходит в проверку", async () => {
    const { probe } = setup();
    const user = userEvent.setup();
    mount();
    await typeUrl(
      user,
      "https://user:ghp_SECRET@github.com/hse-team/paper.git",
    );
    expect(
      screen.getByRole("textbox", { name: "Адрес репозитория" }),
    ).toHaveValue("https://github.com/hse-team/paper.git");
    expect(screen.getByText(/Токен в адресе не нужен/)).toBeInTheDocument();
    await user.click(
      await screen.findByRole("tab", { name: /Публичный репозиторий/ }),
    );
    await user.click(
      screen.getByRole("button", { name: "Проверить репозиторий" }),
    );
    await screen.findByTestId("clone-verdict-ready-full");
    expect(JSON.stringify(probe.mock.calls)).not.toContain("ghp_SECRET");
  });

  it("смена адреса сбрасывает прежний результат проверки", async () => {
    setup();
    const user = userEvent.setup();
    mount();
    await checkPublic(user);
    await screen.findByTestId("clone-verdict-ready-full");
    await user.type(
      screen.getByRole("textbox", { name: "Адрес репозитория" }),
      "2",
    );
    expect(screen.queryByTestId("clone-verdict-ready-full")).toBeNull();
    expect(next).toThrow();
  });

  it("локальная папка не требует доступа и проверяется сразу", async () => {
    const { probe } = setup();
    const user = userEvent.setup();
    mount();
    await typeUrl(user, "/Users/anna/remotes/paper.git");
    expect(screen.queryByTestId("clone-access")).toBeNull();
    await user.click(
      screen.getByRole("button", { name: "Проверить репозиторий" }),
    );
    await screen.findByTestId("clone-verdict-ready-full");
    expect(probe).toHaveBeenCalledWith(
      expect.objectContaining({ credential_id: null }),
    );
  });

  it("с адресом и доступом из окна подключения проверяет репозиторий сам", async () => {
    const { probe } = setup({ credentials: [{ ...PAT, status: "ok" }] });
    mount({
      initialTarget: {
        url: "https://github.com/hse-team/paper",
        credentialId: "cred-pat",
      },
    });
    await screen.findByTestId("clone-verdict-ready-full");
    expect(probe).toHaveBeenCalledTimes(1);
    expect(probe).toHaveBeenCalledWith({
      url: "https://github.com/hse-team/paper",
      credential_id: "cred-pat",
    });
    expect(
      screen.getByRole("textbox", { name: "Адрес репозитория" }),
    ).toHaveValue("https://github.com/hse-team/paper");
  });

  it("«Отмена» уходит из мастера", async () => {
    setup();
    const user = userEvent.setup();
    const { onExit } = mount();
    await screen.findByRole("textbox", { name: "Адрес репозитория" });
    await user.click(screen.getByRole("button", { name: "Отмена" }));
    expect(onExit).toHaveBeenCalledTimes(1);
  });
});

describe("мастер клонирования: профиль автора", () => {
  beforeEach(async () => {
    await resetConnectEnvironment();
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("без имени и e-mail сначала просит представиться, потом ведёт к источнику", async () => {
    setup({ profile: DEFAULT_PROFILE });
    const update = vi
      .spyOn(profileApi, "update")
      .mockResolvedValue(CUSTOM_PROFILE);
    const user = userEvent.setup();
    mount();
    expect(await screen.findByLabelText("Имя")).toBeInTheDocument();
    expect(
      screen.queryByRole("textbox", { name: "Адрес репозитория" }),
    ).toBeNull();
    expect(
      screen.queryByRole("list", { name: "Шаги клонирования" }),
    ).toBeNull();

    await user.type(screen.getByLabelText("Имя"), "Иван Смирнов");
    await user.type(screen.getByLabelText("E-mail"), "ivan@edu.hse.ru");
    await user.click(
      screen.getByRole("button", { name: "Сохранить и продолжить" }),
    );
    expect(update).toHaveBeenCalled();
    expect(
      await screen.findByRole("textbox", { name: "Адрес репозитория" }),
    ).toBeInTheDocument();
  });

  it("если сервер ответил profile_required на запуск, возвращает к профилю", async () => {
    const { startClone } = setup();
    startClone.mockRejectedValue(
      new ApiError("Нужен автор", "profile_required", 409),
    );
    const user = userEvent.setup();
    mount();
    await toFolderStep(user);
    await startCloning(user);
    expect(await screen.findByLabelText("Имя")).toBeInTheDocument();
  });
});

describe("мастер клонирования: папка и запуск", () => {
  beforeEach(async () => {
    await resetConnectEnvironment();
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("подставляет название проекта и папку по умолчанию", async () => {
    const { startClone } = setup();
    const user = userEvent.setup();
    mount();
    await toFolderStep(user);

    expect(screen.getByLabelText(/Название проекта/)).toHaveValue(
      "Курсовая работа",
    );
    await waitFor(() => {
      expect(screen.getByLabelText("Папка на компьютере")).toHaveValue(
        DEFAULT_FOLDER,
      );
    });
    expect(screen.getByTestId("clone-source-summary")).toHaveTextContent(
      "github.com/hse-team/paper",
    );
    expect(
      screen.getByText(
        /история хранится в \.hse-studio\/git, свой \.git не создаётся/,
      ),
    ).toBeInTheDocument();

    await startCloning(user);
    expect(startClone).toHaveBeenCalledWith({
      url: "https://github.com/hse-team/paper",
      credential_id: null,
      folder: DEFAULT_FOLDER,
      name: "Курсовая работа",
    });
    // Идёт загрузка.
    expect(await screen.findByTestId("clone-phases")).toBeInTheDocument();
  });

  it("передаёт выбранную ветку, свою папку и название", async () => {
    const { startClone } = setup({
      probe: makeProbe({
        relation: "studio_project",
        default_branch: "main",
        branches: ["main", "develop"],
      }),
    });
    const user = userEvent.setup();
    mount({ folderSlot: pickerSlot() });
    await checkPublic(user);
    await user.click(await screen.findByRole("button", { name: "develop" }));
    await screen.findByRole("button", { name: "develop", pressed: true });
    await user.click(next());
    await screen.findByLabelText("Папка на компьютере");

    const name = screen.getByLabelText(/Название проекта/);
    await user.clear(name);
    await user.type(name, "Моя копия");
    await user.click(screen.getByRole("button", { name: "Обзор…" }));
    await user.click(
      await screen.findByRole("button", { name: "Выбрать /Users/anna/picked" }),
    );
    expect(screen.getByLabelText("Папка на компьютере")).toHaveValue(
      "/Users/anna/picked",
    );
    await startCloning(user);
    expect(startClone).toHaveBeenCalledWith({
      url: "https://github.com/hse-team/paper",
      credential_id: null,
      branch: "develop",
      folder: "/Users/anna/picked",
      name: "Моя копия",
    });
  });

  it("«Назад» возвращает к источнику с сохранённым результатом проверки", async () => {
    setup();
    const user = userEvent.setup();
    mount();
    await toFolderStep(user);
    await user.click(screen.getByRole("button", { name: "Назад" }));
    expect(
      await screen.findByTestId("clone-verdict-ready-full"),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("textbox", { name: "Адрес репозитория" }),
    ).toHaveValue(URL_TEXT);
  });

  it("папка не пуста: сообщение у поля, шаг остаётся, текст поля не теряется", async () => {
    const { startClone } = setup();
    startClone.mockRejectedValue(
      new ApiError(
        "Папка не пуста. Выбери пустую или новую.",
        "folder_not_empty",
        409,
      ),
    );
    const user = userEvent.setup();
    mount();
    await toFolderStep(user);
    await waitFor(() => {
      expect(screen.getByLabelText("Папка на компьютере")).toHaveValue(
        DEFAULT_FOLDER,
      );
    });
    await startCloning(user);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Папка не пуста");
    expect(screen.getByLabelText("Папка на компьютере")).toHaveAttribute(
      "aria-invalid",
      "true",
    );
    expect(screen.getByLabelText("Папка на компьютере")).toHaveValue(
      DEFAULT_FOLDER,
    );
    expect(screen.queryByTestId("clone-phases")).toBeNull();

    // Новый путь снимает сообщение.
    await user.type(screen.getByLabelText("Папка на компьютере"), "-2");
    expect(screen.queryByText(/Папка не пуста/)).toBeNull();
  });

  it("проект уже открыт: сообщение у поля папки", async () => {
    const { startClone } = setup();
    startClone.mockRejectedValue(
      new ApiError(
        "Этот проект уже есть на компьютере.",
        "project_exists",
        409,
      ),
    );
    const user = userEvent.setup();
    mount();
    await toFolderStep(user);
    await waitFor(() => {
      expect(screen.getByLabelText("Папка на компьютере")).toHaveValue(
        DEFAULT_FOLDER,
      );
    });
    await startCloning(user);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Этот проект уже есть на компьютере",
    );
    expect(screen.getByRole("button", { name: "Клонировать" })).toBeEnabled();
  });

  it("проверка папки: новая, с проектом и файл", async () => {
    setup();
    const user = userEvent.setup();
    const inspect: CloneFolderSlot["useInspect"] = (path) => {
      if (path.includes("picked")) {
        return {
          state: "ready",
          exists: true,
          isDir: true,
          hasProject: true,
          projectName: "Курсовая работа",
        };
      }
      // Так отвечает настоящий сервер: для несуществующего пути is_dir=false.
      return { state: "ready", exists: false, isDir: false };
    };
    mount({ folderSlot: pickerSlot(inspect) });
    await toFolderStep(user);
    expect(
      await screen.findByText(/Такой папки ещё нет: Студия создаст её/),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Клонировать" })).toBeEnabled();

    await user.click(screen.getByRole("button", { name: "Обзор…" }));
    await user.click(
      await screen.findByRole("button", { name: "Выбрать /Users/anna/picked" }),
    );
    expect(
      screen.getByText(/уже есть проект «Курсовая работа»/),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Клонировать" })).toBeDisabled();
  });

  it("предупреждает, что папка лежит в облачном диске", async () => {
    setup();
    vi.spyOn(gitRemoteApi, "getSharedFolder").mockResolvedValue({
      detected: true,
      provider: "yandex_disk",
      root: "/Users/anna/Yandex.Disk",
      evidence: [],
    });
    const user = userEvent.setup();
    mount();
    await toFolderStep(user);
    expect(
      await screen.findByTestId("shared-folder-warning"),
    ).toHaveTextContent("Папка проекта лежит в Яндекс.Диск");
  });
});

describe("мастер клонирования: загрузка", () => {
  beforeEach(async () => {
    await resetConnectEnvironment();
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  const goDownload = async (user: User) => {
    await toFolderStep(user);
    await waitFor(() => {
      expect(screen.getByLabelText("Папка на компьютере")).toHaveValue(
        DEFAULT_FOLDER,
      );
    });
    await startCloning(user);
  };

  it("показывает фазы и процент загрузки", async () => {
    setup({ operation: operation({ phase: "download", percent: 55 }) });
    const user = userEvent.setup();
    mount();
    await goDownload(user);

    const phases = await screen.findByTestId("clone-phases");
    expect(within(phases).getByText("Подключение")).toBeInTheDocument();
    expect(within(phases).getByText("Загрузка истории")).toBeInTheDocument();
    expect(within(phases).getByText("Проверка шаблона")).toBeInTheDocument();
    expect(within(phases).getByText("Регистрация проекта")).toBeInTheDocument();
    expect(within(phases).getByText("55%")).toBeInTheDocument();
    const bar = screen.getByRole("progressbar");
    expect(bar).toHaveAttribute("aria-valuenow", "55");
    expect(screen.getByRole("button", { name: "Отменить" })).toBeEnabled();
  });

  it("на проверке шаблона процента нет, а загрузка уже пройдена", async () => {
    setup({
      operation: operation({ phase: "verify", percent: null, message: null }),
    });
    const user = userEvent.setup();
    mount();
    await goDownload(user);
    const phases = await screen.findByTestId("clone-phases");
    expect(screen.queryByRole("progressbar")).toBeNull();
    expect(
      within(phases)
        .getByText(/Загрузка истории/)
        .closest("li"),
    ).toHaveTextContent(/выполнено|Готово|done/i);
  });

  it("отмена посылает запрос и показывает итог «отменено» с возвратом к папке", async () => {
    const { cancel, getOperation } = setup();
    const user = userEvent.setup();
    mount();
    await goDownload(user);
    await user.click(await screen.findByRole("button", { name: "Отменить" }));
    expect(cancel).toHaveBeenCalledWith(OP_ID);
    getOperation.mockResolvedValue(
      operation({ status: "cancelled", cancellable: false, percent: null }),
    );
    const card = await screen.findByTestId(
      "clone-progress-cancelled",
      undefined,
      {
        timeout: 3000,
      },
    );
    expect(within(card).getByText("Клонирование отменено")).toBeInTheDocument();
    await user.click(
      within(card).getByRole("button", { name: "Попробовать снова" }),
    );
    expect(
      await screen.findByLabelText("Папка на компьютере"),
    ).toBeInTheDocument();
  });

  it("если отменить уже нельзя, объясняет это", async () => {
    const { cancel } = setup();
    cancel.mockRejectedValue(
      new ApiError(
        "Эту операцию уже нельзя отменить.",
        "operation_not_cancellable",
        409,
      ),
    );
    const user = userEvent.setup();
    mount();
    await goDownload(user);
    await user.click(await screen.findByRole("button", { name: "Отменить" }));
    expect(
      await screen.findByText(
        /Отменить уже нельзя: клонирование заканчивается/,
      ),
    ).toBeInTheDocument();
  });

  it("не даёт отменить, пока операция не отменяемая", async () => {
    setup({ operation: operation({ cancellable: false }) });
    const user = userEvent.setup();
    mount();
    await goDownload(user);
    expect(
      await screen.findByRole("button", { name: "Отменить" }),
    ).toBeDisabled();
  });

  it("ошибка папки во время загрузки возвращает к папке с сообщением (folder_not_empty)", async () => {
    setup({
      operation: operation({
        status: "failed",
        cancellable: false,
        percent: null,
        error: {
          code: "folder_not_empty",
          detail: "Папка не пуста. Выбери пустую или новую.",
        },
      }),
    });
    const user = userEvent.setup();
    mount();
    await goDownload(user);
    const card = await screen.findByTestId(
      "clone-progress-failed-folder_not_empty",
    );
    expect(
      within(card).getByText("Не удалось клонировать проект"),
    ).toBeInTheDocument();
    await user.click(
      within(card).getByRole("button", { name: "Выбрать другую папку" }),
    );
    expect(
      await screen.findByLabelText("Папка на компьютере"),
    ).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("Папка не пуста");
  });

  it("проект уже открыт (project_exists) во время загрузки: к папке", async () => {
    setup({
      operation: operation({
        status: "failed",
        cancellable: false,
        error: { code: "project_exists", detail: "Этот проект уже есть." },
      }),
    });
    const user = userEvent.setup();
    mount();
    await goDownload(user);
    const card = await screen.findByTestId(
      "clone-progress-failed-project_exists",
    );
    await user.click(
      within(card).getByRole("button", { name: "Выбрать другую папку" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Этот проект уже есть",
    );
  });

  it("отказ доступа во время загрузки возвращает к источнику", async () => {
    setup({
      operation: operation({
        status: "failed",
        cancellable: false,
        error: { code: "auth_failed", detail: "Сервер отклонил токен" },
      }),
    });
    const user = userEvent.setup();
    mount();
    await goDownload(user);
    const card = await screen.findByTestId("clone-progress-failed-auth_failed");
    await user.click(
      within(card).getByRole("button", { name: "Изменить источник" }),
    );
    expect(
      await screen.findByRole("textbox", { name: "Адрес репозитория" }),
    ).toHaveValue(URL_TEXT);
    expect(await screen.findByTestId("clone-access")).toBeInTheDocument();
  });

  it("неизвестная ошибка: показывает текст сервера и деталь", async () => {
    setup({
      operation: operation({
        status: "failed",
        cancellable: false,
        error: { code: "git_error", detail: "fatal: something odd" },
      }),
    });
    const user = userEvent.setup();
    mount();
    await goDownload(user);
    const card = await screen.findByTestId("clone-progress-failed-git_error");
    expect(
      within(card).getByRole("button", { name: "Попробовать снова" }),
    ).toBeInTheDocument();
  });

  it("успех: «Открыть проект» ведёт в проект и обновляет список проектов", async () => {
    setup({ operation: succeeded() });
    const user = userEvent.setup();
    const { onOpenProject, client } = mount();
    const invalidate = vi.spyOn(client, "invalidateQueries");
    await goDownload(user);
    const card = await screen.findByTestId("clone-progress-done");
    expect(within(card).getByText("Проект загружен")).toBeInTheDocument();
    expect(within(card).getByText(DEFAULT_FOLDER)).toBeInTheDocument();
    expect(within(card).getByText("Для полной работы")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Открыть проект" }));
    expect(onOpenProject).toHaveBeenCalledWith(NEW_PROJECT_ID);
    expect(invalidate).toHaveBeenCalled();
  });

  it("успех, но только для чтения: предупреждает и называет нужную версию", async () => {
    setup({
      operation: succeeded({
        access: "read_only",
        required_studio: "0.4.0",
        warnings: [
          { code: "template_missing", paths: [] },
          { code: "lfs_pointers", paths: ["figures/big.png"] },
        ],
      }),
    });
    const user = userEvent.setup();
    mount();
    await goDownload(user);
    const card = await screen.findByTestId("clone-progress-done");
    expect(within(card).getByText("Только чтение")).toBeInTheDocument();
    expect(within(card).getByText(/Нужна версия 0.4.0/)).toBeInTheDocument();
    expect(
      within(card).getByText(/Шаблона проекта нет в этой версии Студии/),
    ).toBeInTheDocument();
    expect(within(card).getByText(/файлы Git LFS/)).toBeInTheDocument();
  });

  it("не удаётся узнать состояние операции: объясняет и даёт повторить", async () => {
    const { getOperation } = setup();
    getOperation.mockRejectedValue(
      new ApiError("Операция не найдена", "not_found_or_no_access", 404),
    );
    const user = userEvent.setup();
    const { onExit } = mount();
    await goDownload(user);
    const card = await screen.findByTestId("clone-progress-lost");
    expect(card).toHaveTextContent("Не удаётся узнать, как идёт клонирование");
    await user.click(screen.getByRole("button", { name: "К списку проектов" }));
    expect(onExit).toHaveBeenCalled();
  });
});

describe("мастер клонирования: файл bundle", () => {
  beforeEach(async () => {
    await resetConnectEnvironment();
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  const bundleFile = (name: string) =>
    new File(["PACK"], name, { type: "application/octet-stream" });

  const chooseBundle = async (user: User, name: string) => {
    await user.click(await screen.findByRole("tab", { name: "Файл bundle" }));
    const input = await screen.findByTestId("bundle-input");
    await user.upload(input, bundleFile(name));
  };

  it("файл выбирается, название берётся из имени, запуск уходит с файлом", async () => {
    const { startBundle } = setup();
    const user = userEvent.setup();
    mount();
    await chooseBundle(user, "course-paper-20261026-0930.bundle");
    const file = await screen.findByTestId("bundle-file");
    expect(file).toHaveTextContent("course-paper-20261026-0930.bundle");
    // Пароль не нужен.
    expect(screen.queryByLabelText("Пароль файла")).toBeNull();
    await user.click(next());
    await screen.findByLabelText("Папка на компьютере");
    expect(screen.getByLabelText(/Название проекта/)).toHaveValue(
      "course-paper",
    );
    expect(screen.getByTestId("clone-source-summary")).toHaveTextContent(
      "Файл course-paper-20261026-0930.bundle",
    );
    await waitFor(() => {
      expect(screen.getByLabelText("Папка на компьютере")).toHaveValue(
        DEFAULT_FOLDER,
      );
    });
    await startCloning(user);
    await waitFor(() => {
      expect(startBundle).toHaveBeenCalledTimes(1);
    });
    const params = startBundle.mock.calls[0]?.[0];
    expect(params?.file.name).toBe("course-paper-20261026-0930.bundle");
    expect(params?.folder).toBe(DEFAULT_FOLDER);
    expect(params?.name).toBe("course-paper");
    expect(params?.password).toBeUndefined();
    // Для файла у первого шага своё название.
    expect(await screen.findByText("Чтение файла")).toBeInTheDocument();
  });

  it("зашифрованный файл просит пароль и не идёт дальше без него", async () => {
    setup();
    const user = userEvent.setup();
    mount();
    await chooseBundle(user, "paper.bundle.hseenc");
    const password = await screen.findByLabelText("Пароль файла");
    expect(next()).toBeDisabled();
    await user.type(password, "secret");
    expect(next()).toBeEnabled();
    expect(password).toHaveAttribute("type", "password");
    await user.click(screen.getByRole("button", { name: "Показать пароль" }));
    expect(password).toHaveAttribute("type", "text");
  });

  it("чужой тип файла отклоняется", async () => {
    setup();
    const user = userEvent.setup({ applyAccept: false });
    mount();
    await user.click(await screen.findByRole("tab", { name: "Файл bundle" }));
    await user.upload(
      await screen.findByTestId("bundle-input"),
      bundleFile("notes.txt"),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Нужен файл .bundle или .hseenc",
    );
    expect(screen.queryByTestId("bundle-file")).toBeNull();
    expect(next()).toBeDisabled();
  });

  it("файл можно убрать и выбрать другой", async () => {
    setup();
    const user = userEvent.setup();
    mount();
    await chooseBundle(user, "a.bundle");
    await screen.findByTestId("bundle-file");
    await user.click(screen.getByRole("button", { name: "Убрать файл" }));
    expect(screen.getByTestId("bundle-dropzone")).toBeInTheDocument();
    expect(next()).toBeDisabled();
  });

  it("неверный пароль возвращает к источнику с сообщением у поля пароля", async () => {
    const { startBundle } = setup();
    startBundle.mockRejectedValue(
      new ApiError("Пароль не подошёл.", "bundle_password_wrong", 400),
    );
    const user = userEvent.setup();
    mount();
    await chooseBundle(user, "paper.bundle.hseenc");
    await user.type(await screen.findByLabelText("Пароль файла"), "wrong");
    await user.click(next());
    await screen.findByLabelText("Папка на компьютере");
    await waitFor(() => {
      expect(screen.getByLabelText("Папка на компьютере")).toHaveValue(
        DEFAULT_FOLDER,
      );
    });
    await startCloning(user);

    const field = await screen.findByLabelText("Пароль файла");
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Пароль не подошёл",
    );
    // Пароль не хранится после неудачи.
    expect(field).toHaveValue("");
    expect(field).toHaveAttribute("aria-invalid", "true");
  });

  it("повреждённый файл возвращает к источнику с сообщением", async () => {
    const { startBundle } = setup();
    startBundle.mockRejectedValue(
      new ApiError("Файл не похож на архив проекта.", "bundle_invalid", 400),
    );
    const user = userEvent.setup();
    mount();
    await chooseBundle(user, "broken.bundle");
    await user.click(next());
    await screen.findByLabelText("Папка на компьютере");
    await waitFor(() => {
      expect(screen.getByLabelText("Папка на компьютере")).toHaveValue(
        DEFAULT_FOLDER,
      );
    });
    await startCloning(user);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Файл не похож на архив проекта",
    );
    expect(screen.getByTestId("bundle-file")).toBeInTheDocument();
  });

  it("файл можно сменить на вкладку с адресом и вернуться", async () => {
    setup();
    const user = userEvent.setup();
    mount();
    await chooseBundle(user, "a.bundle");
    await user.click(screen.getByRole("tab", { name: "Адрес репозитория" }));
    expect(
      await screen.findByRole("textbox", { name: "Адрес репозитория" }),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: "Файл bundle" }));
    expect(await screen.findByTestId("bundle-file")).toBeInTheDocument();
  });
});

describe("мастер клонирования: жизненный цикл", () => {
  beforeEach(async () => {
    await resetConnectEnvironment();
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("английский интерфейс: заголовки и кнопки переведены", async () => {
    setup();
    const { i18n } = await import("@shared/lib/i18n");
    await act(async () => {
      await i18n.changeLanguage("en");
    });
    mount();
    expect(
      await screen.findByRole("heading", { name: "Clone a project from git" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("tab", { name: "Bundle file" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Check the repository" }),
    ).toBeInTheDocument();
  });
});
