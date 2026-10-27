import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  act,
  cleanup,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {
  afterEach,
  beforeAll,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";
import { apiClient } from "@shared/api";
import { createDemoRouter, installDemoAdapter } from "@shared/api/demo";
import { ConnectRemoteDialog } from "@features/git-remote";
import { GitStatusSchema, useSyncUiStore } from "@entities/git-sync";
import { i18n } from "@shared/lib/i18n";
import { gitDemoRoutes, resetWorld } from "./routes";

// Окно подключения целиком поверх демо-транспорта: те же запросы, что уйдут к
// настоящему бэкенду, и те же ответы, что видит человек в демо-сборке.

const project = { meta: {} as Record<string, unknown> };
vi.mock("@entities/project", async () => ({
  ...(await vi.importActual<Record<string, unknown>>("@entities/project")),
  useProject: () => ({ data: project }),
}));

const PROJECT = "55555555-5555-4555-8555-555555555555";
const TOKEN = "github_pat_DEMO_SECRET_999";

const mount = (mode: "connect" | "fix_access" = "connect") => {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <ConnectRemoteDialog projectId={PROJECT} />
    </QueryClientProvider>,
  );
  act(() => {
    useSyncUiStore.setState({ connectDialog: { mode } });
  });
};

const remoteOf = async () =>
  GitStatusSchema.parse((await apiClient.get(`/projects/${PROJECT}/git`)).data)
    .remote;

const paste = async (
  user: ReturnType<typeof userEvent.setup>,
  label: string,
  value: string,
) => {
  await user.click(await screen.findByLabelText(label));
  await user.paste(value);
};

// Токен набран по символам: вставка целиком проверяет его сразу, это отдельные тесты.
const typeInto = async (
  user: ReturnType<typeof userEvent.setup>,
  label: string,
  value: string,
) => {
  await user.click(await screen.findByLabelText(label));
  await user.keyboard(value);
};

describe("окно подключения поверх демо-транспорта", () => {
  beforeAll(() => {
    installDemoAdapter(apiClient, createDemoRouter(gitDemoRoutes));
  });
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
    useSyncUiStore.setState({ connectDialog: null, popoverOpen: false });
  });
  afterEach(() => {
    cleanup();
    vi.useRealTimers();
  });

  it("новый токен, пустой репозиторий, подключение", async () => {
    resetWorld("not_connected");
    const user = userEvent.setup();
    mount();
    await paste(
      user,
      "Адрес репозитория",
      "https://github.com/hse/empty-paper",
    );
    await user.click(screen.getByRole("button", { name: "Далее" }));
    // Для github.com в демо уже есть сохранённый токен: заводим новый рядом.
    await user.click(await screen.findByLabelText("Добавить новый токен"));
    await typeInto(user, "Токен", TOKEN);
    await user.click(
      screen.getByRole("button", { name: "Сохранить и проверить" }),
    );
    const card = await screen.findByTestId("probe-result-ready-empty");
    expect(card).toHaveTextContent("Репозиторий пуст");
    expect(document.body.innerHTML).not.toContain(TOKEN);
    await user.click(
      within(card).getByRole("button", { name: "Только подключить" }),
    );
    await waitFor(() => {
      expect(useSyncUiStore.getState().connectDialog).toBeNull();
    });
    const remote = await remoteOf();
    expect(remote?.display_url).toBe("https://github.com/hse/empty-paper");
    expect(remote?.credential?.kind).toBe("pat");
  });

  it("слишком крупные файлы останавливают на первом шаге", async () => {
    resetWorld("connect_large_files");
    const user = userEvent.setup();
    mount();
    await paste(user, "Адрес репозитория", "https://github.com/hse/paper");
    const blocker = await screen.findByTestId("over-limit");
    expect(blocker).toHaveTextContent("2 файла крупнее лимита сервера");
    expect(blocker).toHaveTextContent("video/defense-rehearsal.mov");
    expect(screen.getByRole("button", { name: "Далее" })).toBeDisabled();
  });

  it("без автора версий сначала «Представься»", async () => {
    resetWorld("connect_no_profile");
    const user = userEvent.setup();
    mount();
    await user.type(await screen.findByLabelText("Имя"), "Анна Петрова");
    await user.type(screen.getByLabelText("E-mail"), "anna@edu.hse.ru");
    await user.click(
      screen.getByRole("button", { name: "Сохранить и продолжить" }),
    );
    expect(
      await screen.findByLabelText("Адрес репозитория"),
    ).toBeInTheDocument();
  });

  it("предупреждения сценария: NDA, облачный диск, прежние версии", async () => {
    resetWorld("connect_warnings");
    const user = userEvent.setup();
    mount();
    expect(
      await screen.findByTestId("shared-folder-warning"),
    ).toHaveTextContent("Яндекс.Диск");
    await paste(user, "Адрес репозитория", "https://github.com/hse/paper");
    expect(await screen.findByText("Проект помечен NDA")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Далее" })).toBeDisabled();
    await user.click(screen.getByTestId("nda-confirm"));
    expect(screen.getByRole("button", { name: "Далее" })).toBeEnabled();
    expect(screen.getByText(/14 прежних версий/)).toBeInTheDocument();
  });

  it("слова в адресе дают разные исходы проверки", async () => {
    resetWorld("not_connected");
    const user = userEvent.setup();
    mount();
    await paste(user, "Адрес репозитория", "https://github.com/hse/unrelated");
    await user.click(screen.getByRole("button", { name: "Далее" }));
    // Для github.com в демо уже есть сохранённый токен: заводим новый рядом.
    await user.click(await screen.findByLabelText("Добавить новый токен"));
    await typeInto(user, "Токен", TOKEN);
    await user.click(
      screen.getByRole("button", { name: "Сохранить и проверить" }),
    );
    expect(
      await screen.findByTestId("probe-result-unrelated"),
    ).toBeInTheDocument();
    // Объединить истории: подтвердить и подключить.
    await user.click(screen.getByTestId("adopt-confirm"));
    await user.click(
      screen.getByRole("button", { name: "Объединить и подключить" }),
    );
    await waitFor(() => {
      expect(useSyncUiStore.getState().connectDialog).toBeNull();
    });
    expect((await remoteOf())?.display_url).toBe(
      "https://github.com/hse/unrelated",
    );
  });

  it("ssh: незнакомый сервер просит подтвердить ключ, после доверия проверка проходит", async () => {
    resetWorld("not_connected");
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    mount();
    await paste(user, "Адрес репозитория", "git@gitlab.hse.ru:team/empty.git");
    await user.click(screen.getByRole("button", { name: "Далее" }));
    // Для gitlab.hse.ru в демо ключ уже создан и выбран.
    await user.click(
      await screen.findByRole("button", { name: /Я добавил\(а\) ключ/ }),
    );
    const hostDialog = await screen.findByRole("dialog", {
      name: /gitlab.hse.ru подключается впервые/,
    });
    act(() => {
      vi.advanceTimersByTime(3100);
    });
    await user.click(
      within(hostDialog).getByRole("button", { name: "Доверять серверу" }),
    );
    expect(
      await screen.findByTestId("probe-result-ready-empty"),
    ).toBeInTheDocument();
  });

  it("ssh: изменившийся ключ заменяется только после ввода имени сервера", async () => {
    resetWorld("not_connected");
    const user = userEvent.setup();
    mount();
    await paste(user, "Адрес репозитория", "git@github.com:hse/changed.git");
    await user.click(screen.getByRole("button", { name: "Далее" }));
    await user.click(
      await screen.findByRole("button", { name: "Создать ключ" }),
    );
    await user.click(
      await screen.findByRole("button", { name: /Я добавил\(а\) ключ/ }),
    );
    const hostDialog = await screen.findByRole("dialog", {
      name: /Ключ сервера github.com изменился/,
    });
    const replace = within(hostDialog).getByRole("button", {
      name: "Заменить ключ",
    });
    expect(replace).toBeDisabled();
    await user.type(
      within(hostDialog).getByLabelText(/введи имя сервера/),
      "github.com",
    );
    await user.click(replace);
    expect(
      await screen.findByTestId("probe-result-ready-empty"),
    ).toBeInTheDocument();
  });

  it("обновление доступа после отказа сервера возвращает синхронизацию в строй", async () => {
    resetWorld("auth_failed");
    const user = userEvent.setup();
    mount("fix_access");
    await user.click(await screen.findByLabelText("Новый токен"));
    await user.keyboard(TOKEN);
    await user.click(
      screen.getByRole("button", { name: "Сохранить и проверить" }),
    );
    const card = await screen.findByTestId("probe-result-ready-empty");
    await user.click(
      within(card).getByRole("button", { name: "Сохранить доступ" }),
    );
    await waitFor(() => {
      expect(useSyncUiStore.getState().connectDialog).toBeNull();
    });
    const status = GitStatusSchema.parse(
      (await apiClient.get(`/projects/${PROJECT}/git`)).data,
    );
    expect(status.ui_state).not.toBe("auth_failed");
    expect(status.health).toBe("ok");
  });

  it("GitLab.com: ссылка на токен, вставка проверяется сразу, права названы", async () => {
    resetWorld("provider_gitlab_com");
    const user = userEvent.setup();
    mount();
    await paste(
      user,
      "Адрес репозитория",
      "https://gitlab.com/hse/empty-paper.git",
    );
    expect(screen.getByTestId("provider-chip")).toHaveTextContent("GitLab");
    await user.click(screen.getByRole("button", { name: "Далее" }));
    const link = await screen.findByTestId("token-create-link");
    expect(link).toHaveTextContent("Создать токен на GitLab");
    expect(
      new URL(link.getAttribute("href") ?? "").searchParams.get("scopes"),
    ).toBe("read_repository,write_repository");
    await user.click(screen.getByLabelText("Токен"));
    await user.paste("glpat-demo-token-123456");
    const card = await screen.findByTestId("token-check-sufficient");
    expect(card).toHaveTextContent("ivan-smirnov");
    expect(card).toHaveTextContent("write_repository");
    expect(document.body.innerHTML).not.toContain("glpat-demo-token-123456");
    await user.click(screen.getByRole("button", { name: "Проверить" }));
    expect(
      await screen.findByTestId("probe-result-ready-empty"),
    ).toBeInTheDocument();
  });

  it("старый GitLab: заметка о версии, права проверить нельзя, но подключиться можно", async () => {
    resetWorld("provider_gitlab_old");
    const user = userEvent.setup();
    mount();
    await paste(
      user,
      "Адрес репозитория",
      "https://gitlab.old.hse.ru/team/empty-paper.git",
    );
    expect(await screen.findByTestId("provider-version")).toHaveTextContent(
      "v13.12",
    );
    await user.click(screen.getByRole("button", { name: "Далее" }));
    const note = await screen.findByTestId("gitlab-legacy-note");
    expect(note).toHaveTextContent("GitLab 13.12.2");
    expect(
      new URL(
        screen.getByTestId("token-create-link").getAttribute("href") ?? "",
      ).pathname,
    ).toBe("/-/profile/personal_access_tokens");
    await user.click(await screen.findByLabelText("Токен"));
    await user.paste("glpat-demo-token-123456");
    expect(
      await screen.findByTestId("token-check-unknown"),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Проверить" }));
    const ready = await screen.findByTestId("probe-result-ready-empty");
    expect(ready).toHaveTextContent("GitLab 13.12");
  });

  it("внутренний сервер: окно сертификата, затем проверка проходит", async () => {
    resetWorld("provider_tls_ca");
    const user = userEvent.setup();
    mount();
    await paste(
      user,
      "Адрес репозитория",
      "https://gitlab.hse.local/team/empty-paper.git",
    );
    await user.click(screen.getByRole("button", { name: "Далее" }));
    await typeInto(user, "Токен", "glpat-demo-token-123456");
    await user.click(
      screen.getByRole("button", { name: "Сохранить и проверить" }),
    );
    const dialog = await screen.findByRole("dialog", {
      name: /Сертификат gitlab.hse.local не из известного центра/,
    });
    await user.click(within(dialog).getByTestId("tls-ca-text"));
    await user.paste(
      "-----BEGIN CERTIFICATE-----\nMIIBdemo\n-----END CERTIFICATE-----",
    );
    await user.click(within(dialog).getByTestId("tls-submit"));
    expect(
      await screen.findByTestId("probe-result-ready-empty"),
    ).toBeInTheDocument();
  });

  it("самоподписанный сервер: отпечаток закрепляется после отметки о сверке", async () => {
    resetWorld("provider_tls_selfsigned");
    const user = userEvent.setup();
    mount();
    await paste(
      user,
      "Адрес репозитория",
      "https://gitlab.lab.local/team/empty-paper.git",
    );
    await user.click(screen.getByRole("button", { name: "Далее" }));
    await typeInto(user, "Токен", "glpat-demo-token-123456");
    await user.click(
      screen.getByRole("button", { name: "Сохранить и проверить" }),
    );
    const dialog = await screen.findByRole("dialog", {
      name: /Сертификат gitlab.lab.local не из известного центра/,
    });
    // Самоподписанный сертификат: сразу предлагается закрепить его отпечаток.
    expect(within(dialog).getByTestId("tls-certificate")).toHaveTextContent(
      "самоподписанный",
    );
    const submit = within(dialog).getByTestId("tls-submit");
    expect(submit).toBeDisabled();
    await user.click(within(dialog).getByTestId("tls-pin-confirm"));
    await user.click(submit);
    expect(
      await screen.findByTestId("probe-result-ready-empty"),
    ).toBeInTheDocument();
  });

  it("сертификат сменился: видны оба отпечатка, новый закрепляется после ввода имени сервера", async () => {
    resetWorld("provider_tls_pin_changed");
    const user = userEvent.setup();
    mount();
    await paste(
      user,
      "Адрес репозитория",
      "https://gitlab.rotated.local/team/empty-paper.git",
    );
    await user.click(screen.getByRole("button", { name: "Далее" }));
    await typeInto(user, "Токен", "glpat-demo-token-123456");
    await user.click(
      screen.getByRole("button", { name: "Сохранить и проверить" }),
    );
    const dialog = await screen.findByRole("dialog", {
      name: /Сертификат gitlab.rotated.local изменился/,
    });
    const compare = within(dialog).getByTestId("tls-compare");
    expect(
      within(compare).getByDisplayValue(
        "SHA256:0ldPinnedCertificateFingerprintNoLongerPresented123",
      ),
    ).toBeInTheDocument();
    expect(
      within(compare).getByDisplayValue(/^SHA256:b1Kq0vU7m4Zl9Xc2/),
    ).toBeInTheDocument();
    await user.click(within(dialog).getByTestId("tls-pin-confirm"));
    await user.type(
      within(dialog).getByLabelText(/введи имя сервера/),
      "gitlab.rotated.local",
    );
    await user.click(within(dialog).getByTestId("tls-submit"));
    expect(
      await screen.findByTestId("probe-result-ready-empty"),
    ).toBeInTheDocument();
  });

  it("токену не хватает прав: проверка называет право, подключиться всё равно можно", async () => {
    resetWorld("token_narrow");
    const user = userEvent.setup();
    mount();
    await paste(
      user,
      "Адрес репозитория",
      "https://gitlab.com/hse/empty-paper.git",
    );
    await user.click(screen.getByRole("button", { name: "Далее" }));
    await user.click(await screen.findByLabelText("Токен"));
    await user.paste("glpat-demo-token-123456");
    expect(
      await screen.findByTestId("token-check-too_narrow"),
    ).toHaveTextContent("write_repository");
    await user.click(screen.getByRole("button", { name: "Проверить" }));
    const ready = await screen.findByTestId("probe-result-ready-empty");
    expect(ready).toHaveTextContent("добавь write_repository");
  });

  it("срок токена истёк: проверка говорит об этом, а проверка адреса останавливает", async () => {
    resetWorld("token_expired");
    const user = userEvent.setup();
    mount();
    await paste(
      user,
      "Адрес репозитория",
      "https://gitlab.com/hse/empty-paper.git",
    );
    await user.click(screen.getByRole("button", { name: "Далее" }));
    await user.click(await screen.findByLabelText("Токен"));
    await user.paste("glpat-demo-token-123456");
    expect(
      await screen.findByTestId("token-check-expired"),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Проверить" }));
    expect(
      await screen.findByTestId("probe-result-token_expired"),
    ).toBeInTheDocument();
  });

  it("тип сервера по ответу сервера и подсказка у незнакомого хоста", async () => {
    resetWorld("provider_api_detect");
    const user = userEvent.setup();
    mount();
    await paste(
      user,
      "Адрес репозитория",
      "https://forge.hse.ru/team/empty-paper.git",
    );
    expect(screen.getByTestId("provider-unknown-hint")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Далее" }));
    await user.click(await screen.findByLabelText("Токен"));
    await user.paste("glpat-demo-token-123456");
    await screen.findByTestId("token-check-sufficient");
    await user.click(screen.getByRole("button", { name: "Проверить" }));
    const ready = await screen.findByTestId("probe-result-ready-empty");
    expect(ready).toHaveTextContent("GitLab 16.11");
  });
  it("deploy-ключ: создаётся для репозитория, ссылка на его страницу, подключение проходит", async () => {
    resetWorld("not_connected");
    const user = userEvent.setup();
    mount();
    await paste(
      user,
      "Адрес репозитория",
      "https://github.com/hse/empty-paper",
    );
    await user.click(screen.getByRole("button", { name: "Далее" }));
    await user.click(await screen.findByRole("tab", { name: /Deploy-ключ/ }));
    expect(await screen.findByTestId("deploy-repo")).toHaveTextContent(
      "hse/empty-paper",
    );
    await user.click(
      screen.getByRole("button", { name: "Создать deploy-ключ" }),
    );
    const keyField = await screen.findByLabelText("Публичный ключ", {
      selector: "textarea",
    });
    expect((keyField as HTMLTextAreaElement).value).toContain("ssh-ed25519");
    expect(
      screen.getByRole("link", { name: /Открыть страницу deploy-ключей/ }),
    ).toHaveAttribute(
      "href",
      "https://github.com/hse/empty-paper/settings/keys/new",
    );
    await user.click(
      screen.getByRole("button", { name: /Я добавил\(а\) ключ/ }),
    );
    const card = await screen.findByTestId("probe-result-ready-empty");
    await user.click(
      within(card).getByRole("button", { name: "Только подключить" }),
    );
    await waitFor(() => {
      expect(useSyncUiStore.getState().connectDialog).toBeNull();
    });
    const remote = await remoteOf();
    expect(remote?.credential?.kind).toBe("ssh_key");
    expect(remote?.credential?.label).toBe("Deploy-ключ: hse/empty-paper");
  });

  it("публичный репозиторий: подключается без доступа, версии только приходят", async () => {
    resetWorld("not_connected");
    const user = userEvent.setup();
    mount();
    await paste(
      user,
      "Адрес репозитория",
      "https://github.com/hse/empty-paper",
    );
    await user.click(screen.getByRole("button", { name: "Далее" }));
    await user.click(
      await screen.findByRole("tab", { name: /Публичный репозиторий/ }),
    );
    await user.click(screen.getByRole("button", { name: "Проверить" }));
    const card = await screen.findByTestId("probe-result-ready-empty");
    expect(card).toHaveTextContent(/версии будут только приходить/);
    await user.click(
      within(card).getByRole("button", { name: "Только подключить" }),
    );
    await waitFor(() => {
      expect(useSyncUiStore.getState().connectDialog).toBeNull();
    });
    expect((await remoteOf())?.credential ?? null).toBeNull();
  });
});
