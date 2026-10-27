import { cleanup, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@shared/api";
import { useToastStore } from "@shared/lib";
import { settingsApi, type SettingsData } from "@entities/app-settings";
import {
  gitRemoteApi,
  type GitCredential,
  type GitHost,
  type SecretsStatus,
} from "@entities/git-remote";
import { CHECK_OK, PAT, SSH_KEY } from "../testing/connectFixtures";
import {
  installPointerPolyfills,
  renderSettings,
  resetSettingsEnvironment,
} from "../testing/renderSettings";
import { GitAccessSection } from "./GitAccessSection";

const USED_PAT: GitCredential = {
  ...PAT,
  status: "ok",
  used_by: [
    { project_id: "p-1", name: "Курсовая работа" },
    { project_id: "p-2", name: "Диплом" },
  ],
};

const GITHUB_HOST: GitHost = {
  host: "github.com",
  port: null,
  key_types: ["ssh-ed25519", "ssh-rsa"],
  fingerprints_sha256: ["SHA256:edEdEdEd", "SHA256:rsaRsaRsa"],
  added_at: "2026-10-20T10:00:00Z",
};

const GITLAB_HOST: GitHost = {
  host: "git.hse.ru",
  port: 2222,
  key_types: ["ssh-ed25519"],
  fingerprints_sha256: ["SHA256:hseHseHse"],
  added_at: "2026-10-25T10:00:00Z",
};

const HEALTHY: SecretsStatus = {
  ok: true,
  source: "file",
  permissions_enforced: true,
  credentials_total: 2,
  credentials_unreadable: 0,
  data_dir_shared_folder: null,
};

type Setup = {
  credentials?: GitCredential[];
  hosts?: GitHost[];
  secrets?: SecretsStatus;
};

const setup = ({
  credentials = [USED_PAT, SSH_KEY],
  hosts = [GITHUB_HOST, GITLAB_HOST],
  secrets = HEALTHY,
}: Setup = {}) => {
  vi.spyOn(gitRemoteApi, "listCredentials").mockResolvedValue(credentials);
  vi.spyOn(gitRemoteApi, "listHosts").mockResolvedValue(hosts);
  vi.spyOn(gitRemoteApi, "listHostSettings").mockResolvedValue([]);
  vi.spyOn(gitRemoteApi, "checkCredential").mockResolvedValue(CHECK_OK);
  vi.spyOn(gitRemoteApi, "getSecretsStatus").mockResolvedValue(secrets);
  vi.spyOn(settingsApi, "get").mockResolvedValue({
    git_fetch_interval_s: 300,
  } as unknown as SettingsData);
};

const card = async (label: string): Promise<HTMLElement> => {
  // Подпись доступа есть и в карточке, и в списке сервера: нужна карточка.
  const titles = await screen.findAllByText(label);
  for (const title of titles) {
    const element = title.closest("[data-testid='credential-card']");
    if (element instanceof HTMLElement) return element;
  }
  throw new Error("нет карточки");
};

describe("раздел «Доступ к репозиториям»", () => {
  beforeEach(async () => {
    await resetSettingsEnvironment();
    installPointerPolyfills();
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("показывает заголовок и все блоки", async () => {
    setup();
    renderSettings(<GitAccessSection />);
    expect(
      screen.getByRole("heading", { name: "Доступ к репозиториям" }),
    ).toBeInTheDocument();
    expect(await screen.findByText("Токены и ключи")).toBeInTheDocument();
    expect(screen.getByText("Доверенные серверы")).toBeInTheDocument();
    expect(await screen.findByText("Шифрование")).toBeInTheDocument();
    expect(
      screen.getByText("Фоновая проверка по умолчанию"),
    ).toBeInTheDocument();
    expect(await screen.findByText("Серверы git")).toBeInTheDocument();
    // Входа через браузер нет ни в виде карточки, ни в виде обещания.
    expect(screen.queryByTestId("browser-login-card")).toBeNull();
    expect(screen.queryByText("Скоро")).toBeNull();
  });

  it("пока данные грузятся, показывает индикаторы", () => {
    vi.spyOn(gitRemoteApi, "listCredentials").mockReturnValue(
      new Promise<never>(() => undefined),
    );
    vi.spyOn(gitRemoteApi, "listHosts").mockReturnValue(
      new Promise<never>(() => undefined),
    );
    vi.spyOn(gitRemoteApi, "getSecretsStatus").mockReturnValue(
      new Promise<never>(() => undefined),
    );
    renderSettings(<GitAccessSection />);
    expect(screen.getAllByRole("status").length).toBeGreaterThanOrEqual(3);
  });

  it("при сбое блока даёт повторить именно его", async () => {
    setup();
    const user = userEvent.setup();
    const list = vi
      .spyOn(gitRemoteApi, "listHosts")
      .mockRejectedValueOnce(new Error("boom"))
      .mockResolvedValue([GITHUB_HOST]);
    renderSettings(<GitAccessSection />);
    const alert = await screen.findByRole("alert");
    await user.click(within(alert).getByRole("button", { name: "Повторить" }));
    expect(await screen.findByTestId("known-hosts")).toBeInTheDocument();
    expect(list).toHaveBeenCalledTimes(2);
  });

  describe("токены и ключи", () => {
    it("карточки называют вид, статус, сервер и последнее использование", async () => {
      setup();
      renderSettings(<GitAccessSection />);
      const pat = await card("GitHub, рабочий");
      expect(within(pat).getByText("Токен")).toBeInTheDocument();
      expect(within(pat).getByText("Работает")).toBeInTheDocument();
      expect(within(pat).getByText("github.com")).toBeInTheDocument();
      expect(within(pat).getByText(/github_pat…/)).toBeInTheDocument();
      expect(within(pat).getByText(/Использован/)).toBeInTheDocument();
      const key = await card(SSH_KEY.label);
      expect(within(key).getByText("Ключ ssh")).toBeInTheDocument();
      expect(within(key).getByText("Ещё не проверялся")).toBeInTheDocument();
      expect(within(key).getByText(/Ещё не использовался/)).toBeInTheDocument();
      expect(within(key).getByText("Не используется")).toBeInTheDocument();
    });

    it("отказанный сервером доступ подсказывает, что делать", async () => {
      setup({ credentials: [{ ...PAT, status: "auth_failed" }] });
      renderSettings(<GitAccessSection />);
      const pat = await card("GitHub, рабочий");
      expect(within(pat).getByText("Отклонён сервером")).toBeInTheDocument();
      expect(
        within(pat).getByText(
          "Сервер не принял этот доступ. Замени токен или ключ.",
        ),
      ).toBeInTheDocument();
    });

    it("без доступов говорит, откуда они берутся", async () => {
      setup({ credentials: [] });
      renderSettings(<GitAccessSection />);
      expect(await screen.findByText(/Доступов пока нет/)).toBeInTheDocument();
    });

    it("список проектов открывается во всплывающем окне со ссылками на их настройки", async () => {
      setup();
      const user = userEvent.setup();
      renderSettings(<GitAccessSection />);
      const pat = await card("GitHub, рабочий");
      await user.click(
        within(pat).getByRole("button", { name: "Используется в 2 проектах" }),
      );
      const popover = await screen.findByRole("dialog", {
        name: "Проекты с этим доступом",
      });
      const link = within(popover).getByRole("link", { name: "Диплом" });
      expect(link).toHaveAttribute(
        "href",
        "/projects/p-2/project-settings/sync",
      );
    });

    it("публичный ключ показывается по кнопке", async () => {
      setup();
      const user = userEvent.setup();
      renderSettings(<GitAccessSection />);
      const key = await card(SSH_KEY.label);
      await user.click(
        within(key).getByRole("button", { name: "Показать публичный ключ" }),
      );
      expect(within(key).getByLabelText("Публичный ключ")).toHaveValue(
        SSH_KEY.public_key,
      );
      expect(
        within(key).queryByRole("button", { name: "Заменить токен" }),
      ).toBeNull();
    });
  });

  describe("замена токена", () => {
    const open = async () => {
      setup();
      const user = userEvent.setup();
      renderSettings(<GitAccessSection />);
      const pat = await card("GitHub, рабочий");
      await user.click(
        within(pat).getByRole("button", { name: "Заменить токен" }),
      );
      const dialog = await screen.findByRole("dialog", {
        name: "Заменить токен",
      });
      return { user, dialog };
    };

    it("кнопка «Заменить» ждёт токен и не принимает пустой", async () => {
      const { dialog } = await open();
      expect(
        within(dialog).getByRole("button", { name: "Заменить" }),
      ).toBeDisabled();
    });

    it("отправляет только новый токен, стирает его и закрывается", async () => {
      const { user, dialog } = await open();
      const update = vi
        .spyOn(gitRemoteApi, "updateCredential")
        .mockResolvedValue({ ...USED_PAT, status: "unverified" });
      const field = within(dialog).getByLabelText("Новый токен");
      expect(field).toHaveAttribute("type", "password");
      await user.type(field, "  github_pat_NEW123  ");
      await user.click(
        within(dialog).getByRole("button", { name: "Заменить" }),
      );
      await waitFor(() => {
        expect(update).toHaveBeenCalledWith("cred-pat", {
          token: "github_pat_NEW123",
        });
      });
      await waitFor(() => {
        expect(
          screen.queryByRole("dialog", { name: "Заменить токен" }),
        ).toBeNull();
      });
      expect(
        useToastStore
          .getState()
          .toasts.some((toast) => toast.message === "Токен заменён"),
      ).toBe(true);
    });

    it("при отказе сервера показывает причину и очищает поле токена", async () => {
      const { user, dialog } = await open();
      vi.spyOn(gitRemoteApi, "updateCredential").mockRejectedValue(
        new ApiError("Токен слишком короткий.", "credential_invalid", 422),
      );
      const field = within(dialog).getByLabelText("Новый токен");
      await user.type(field, "short");
      await user.click(
        within(dialog).getByRole("button", { name: "Заменить" }),
      );
      expect(await within(dialog).findByRole("alert")).toBeInTheDocument();
      expect(field).toHaveValue("");
      expect(
        screen.getByRole("dialog", { name: "Заменить токен" }),
      ).toBeInTheDocument();
    });

    it("токен можно показать и скрыть", async () => {
      const { user, dialog } = await open();
      await user.type(within(dialog).getByLabelText("Новый токен"), "abc");
      await user.click(
        within(dialog).getByRole("button", { name: "Показать токен" }),
      );
      expect(within(dialog).getByLabelText("Новый токен")).toHaveAttribute(
        "type",
        "text",
      );
    });
  });

  describe("удаление доступа", () => {
    const open = async (credential: GitCredential) => {
      setup({ credentials: [credential] });
      const user = userEvent.setup();
      renderSettings(<GitAccessSection />);
      const element = await card(credential.label);
      await user.click(
        within(element).getByRole("button", {
          name: `Удалить доступ «${credential.label}»`,
        }),
      );
      const dialog = await screen.findByRole("dialog", {
        name: `Удалить доступ «${credential.label}»?`,
      });
      return { user, dialog };
    };

    it("перечисляет проекты, которые останутся без доступа", async () => {
      const { dialog } = await open(USED_PAT);
      const list = within(dialog).getByRole("list", {
        name: "Эти проекты потеряют доступ",
      });
      expect(
        within(list)
          .getAllByRole("listitem")
          .map((item) => item.textContent),
      ).toEqual(["Курсовая работа", "Диплом"]);
      expect(
        within(dialog).getByRole("button", {
          name: "Удалить и оставить проекты без доступа",
        }),
      ).toBeInTheDocument();
    });

    it("для используемого доступа удаляет с force", async () => {
      const { user, dialog } = await open(USED_PAT);
      const remove = vi
        .spyOn(gitRemoteApi, "deleteCredential")
        .mockResolvedValue();
      await user.click(
        within(dialog).getByRole("button", {
          name: "Удалить и оставить проекты без доступа",
        }),
      );
      await waitFor(() => {
        expect(remove).toHaveBeenCalledWith("cred-pat", true);
      });
      expect(
        useToastStore
          .getState()
          .toasts.some((toast) => toast.message === "Доступ удалён"),
      ).toBe(true);
    });

    it("для неиспользуемого говорит об этом и удаляет без force", async () => {
      const { user, dialog } = await open(SSH_KEY);
      expect(
        within(dialog).getByText("Ни один проект его не использует."),
      ).toBeInTheDocument();
      const remove = vi
        .spyOn(gitRemoteApi, "deleteCredential")
        .mockResolvedValue();
      await user.click(within(dialog).getByRole("button", { name: "Удалить" }));
      await waitFor(() => {
        expect(remove).toHaveBeenCalledWith(SSH_KEY.id, false);
      });
    });

    it("если за это время доступ заняли, показывает свежий список и спрашивает ещё раз", async () => {
      const { user, dialog } = await open(SSH_KEY);
      const remove = vi
        .spyOn(gitRemoteApi, "deleteCredential")
        .mockRejectedValueOnce(
          new ApiError("Доступ используется.", "credential_in_use", 409, {
            projects: [{ project_id: "p-9", name: "Новый проект" }],
          }),
        )
        .mockResolvedValue();
      await user.click(within(dialog).getByRole("button", { name: "Удалить" }));
      expect(
        await within(dialog).findByText("Новый проект"),
      ).toBeInTheDocument();
      expect(remove).toHaveBeenCalledTimes(1);
      await user.click(
        within(dialog).getByRole("button", {
          name: "Удалить и оставить проекты без доступа",
        }),
      );
      await waitFor(() => {
        expect(remove).toHaveBeenLastCalledWith(SSH_KEY.id, true);
      });
    });

    it("отмена ничего не удаляет", async () => {
      const { user, dialog } = await open(USED_PAT);
      const remove = vi.spyOn(gitRemoteApi, "deleteCredential");
      await user.click(within(dialog).getByRole("button", { name: "Отмена" }));
      await waitFor(() => {
        expect(screen.queryByRole("dialog")).toBeNull();
      });
      expect(remove).not.toHaveBeenCalled();
    });
  });

  describe("доверенные серверы", () => {
    it("таблица называет сервер с портом, ключи и отпечатки", async () => {
      setup();
      renderSettings(<GitAccessSection />);
      const table = await screen.findByTestId("known-hosts");
      expect(
        within(table).getByRole("rowheader", { name: "github.com" }),
      ).toBeInTheDocument();
      expect(
        within(table).getByRole("rowheader", { name: "git.hse.ru:2222" }),
      ).toBeInTheDocument();
      expect(within(table).getByText("SHA256:rsaRsaRsa")).toBeInTheDocument();
      expect(within(table).getAllByText("ssh-ed25519")).toHaveLength(2);
    });

    it("без серверов объясняет, откуда они появятся", async () => {
      setup({ hosts: [] });
      renderSettings(<GitAccessSection />);
      expect(
        await screen.findByText(/Пока ни одного сервера/),
      ).toBeInTheDocument();
    });

    it("«Забыть» просит подтверждение и убирает сервер с портом", async () => {
      setup();
      const user = userEvent.setup();
      const remove = vi.spyOn(gitRemoteApi, "deleteHost").mockResolvedValue();
      renderSettings(<GitAccessSection />);
      await user.click(
        await screen.findByRole("button", {
          name: "Забыть сервер git.hse.ru:2222",
        }),
      );
      const dialog = await screen.findByRole("dialog", {
        name: "Забыть сервер git.hse.ru:2222?",
      });
      expect(remove).not.toHaveBeenCalled();
      await user.click(
        within(dialog).getByRole("button", { name: "Забыть сервер" }),
      );
      await waitFor(() => {
        expect(remove).toHaveBeenCalledWith("git.hse.ru", 2222);
      });
    });

    it("отмена в окне не трогает сервер", async () => {
      setup();
      const user = userEvent.setup();
      const remove = vi.spyOn(gitRemoteApi, "deleteHost").mockResolvedValue();
      renderSettings(<GitAccessSection />);
      await user.click(
        await screen.findByRole("button", { name: "Забыть сервер github.com" }),
      );
      const dialog = await screen.findByRole("dialog");
      await user.click(within(dialog).getByRole("button", { name: "Отмена" }));
      expect(remove).not.toHaveBeenCalled();
    });

    it("сбой показывает причину в окне", async () => {
      setup();
      const user = userEvent.setup();
      vi.spyOn(gitRemoteApi, "deleteHost").mockRejectedValue(
        new ApiError("Нет прав.", "git_error", 500),
      );
      renderSettings(<GitAccessSection />);
      await user.click(
        await screen.findByRole("button", { name: "Забыть сервер github.com" }),
      );
      const dialog = await screen.findByRole("dialog");
      await user.click(
        within(dialog).getByRole("button", { name: "Забыть сервер" }),
      );
      expect(await within(dialog).findByRole("alert")).toBeInTheDocument();
    });
  });

  describe("шифрование", () => {
    it("в спокойном состоянии предупреждений нет", async () => {
      setup();
      renderSettings(<GitAccessSection />);
      const encryption = await screen.findByRole("region", {
        name: "Шифрование",
      });
      expect(within(encryption).getByText("Включено")).toBeInTheDocument();
      expect(
        within(encryption).getByText("Хранится доступов: 2"),
      ).toBeInTheDocument();
      expect(
        within(encryption).getByText(/Ключ шифрования лежит в файле/),
      ).toBeInTheDocument();
      expect(
        within(encryption).getByText(/закрыт от других пользователей/),
      ).toBeInTheDocument();
      expect(within(encryption).queryByRole("alert")).toBeNull();
      expect(within(encryption).queryByRole("status")).toBeNull();
    });

    it("папка данных в облачном диске даёт жёлтое предупреждение с путём", async () => {
      setup({
        secrets: {
          ...HEALTHY,
          data_dir_shared_folder: {
            provider: "yandex_disk",
            root: "/Users/ivan/Yandex.Disk",
          },
        },
      });
      renderSettings(<GitAccessSection />);
      const encryption = await screen.findByRole("region", {
        name: "Шифрование",
      });
      const warning = within(encryption).getByRole("status");
      expect(warning).toHaveTextContent("Яндекс.Диск");
      expect(warning).toHaveTextContent("HSE_STUDIO__SECRETS__KEY_FILE");
      expect(warning).toHaveTextContent("/Users/ivan/Yandex.Disk");
    });

    it("права на файл ключа не ограничены: предупреждение, а плюса про права нет", async () => {
      setup({ secrets: { ...HEALTHY, permissions_enforced: false } });
      renderSettings(<GitAccessSection />);
      const encryption = await screen.findByRole("region", {
        name: "Шифрование",
      });
      expect(encryption).toHaveTextContent("не закрыт от других пользователей");
      expect(encryption).not.toHaveTextContent(
        "закрыт от других пользователей этого компьютера",
      );
    });

    it("нечитаемые доступы дают красную плашку с правильным числом", async () => {
      setup({ secrets: { ...HEALTHY, credentials_unreadable: 2 } });
      renderSettings(<GitAccessSection />);
      const encryption = await screen.findByRole("region", {
        name: "Шифрование",
      });
      expect(within(encryption).getByRole("alert")).toHaveTextContent(
        "Не удалось прочитать 2 доступа",
      );
    });

    it("недоступное хранилище: красная плашка и метка «Недоступно»", async () => {
      setup({ secrets: { ...HEALTHY, ok: false } });
      renderSettings(<GitAccessSection />);
      const encryption = await screen.findByRole("region", {
        name: "Шифрование",
      });
      expect(within(encryption).getByText("Недоступно")).toBeInTheDocument();
      expect(within(encryption).getByRole("alert")).toHaveTextContent(
        "Хранилище секретов недоступно",
      );
    });

    it("ключ из переменной окружения описывается иначе", async () => {
      setup({ secrets: { ...HEALTHY, source: "env" } });
      renderSettings(<GitAccessSection />);
      const encryption = await screen.findByRole("region", {
        name: "Шифрование",
      });
      expect(encryption).toHaveTextContent("задан переменной окружения");
    });
  });

  describe("интервал по умолчанию", () => {
    it("показывает действующее значение и сохраняет новое", async () => {
      setup();
      const user = userEvent.setup();
      const update = vi.spyOn(settingsApi, "update").mockResolvedValue({
        git_fetch_interval_s: 600,
      } as unknown as SettingsData);
      renderSettings(<GitAccessSection />);
      const select = await screen.findByRole("combobox", {
        name: "Интервал по умолчанию",
      });
      await waitFor(() => {
        expect(select).toHaveTextContent("5 мин");
      });
      await user.click(select);
      await user.click(await screen.findByRole("option", { name: "10 мин" }));
      await waitFor(() => {
        expect(update).toHaveBeenCalledWith({ git_fetch_interval_s: 600 });
      });
    });

    it("можно выключить проверку совсем", async () => {
      setup();
      const user = userEvent.setup();
      const update = vi.spyOn(settingsApi, "update").mockResolvedValue({
        git_fetch_interval_s: 0,
      } as unknown as SettingsData);
      renderSettings(<GitAccessSection />);
      await user.click(
        await screen.findByRole("combobox", { name: "Интервал по умолчанию" }),
      );
      await user.click(
        await screen.findByRole("option", { name: "Выключена" }),
      );
      await waitFor(() => {
        expect(update).toHaveBeenCalledWith({ git_fetch_interval_s: 0 });
      });
    });
  });

  it("токены, которым нужна замена, собраны в одно предупреждение", async () => {
    const day = 24 * 3600 * 1000;
    setup({
      credentials: [
        { ...PAT, id: "a", label: "Отклонён", status: "auth_failed" },
        {
          ...PAT,
          id: "b",
          label: "Просрочен",
          status: "ok",
          expires_at: new Date(Date.now() - 3 * day).toISOString(),
        },
        {
          ...PAT,
          id: "c",
          label: "Скоро",
          status: "ok",
          expires_at: new Date(Date.now() + 5 * day).toISOString(),
        },
        {
          ...PAT,
          id: "d",
          label: "Здоров",
          status: "ok",
          expires_at: new Date(Date.now() + 120 * day).toISOString(),
        },
      ],
    });
    renderSettings(<GitAccessSection />);
    expect(
      await screen.findByText(/3 токена требуют внимания/),
    ).toBeInTheDocument();
    const expired = await card("Просрочен");
    expect(within(expired).getByTestId("expiry-badge")).toHaveAttribute(
      "data-state",
      "expired",
    );
    expect(
      within(expired).getByRole("button", { name: "Заменить токен" }),
    ).toHaveClass("primary");
    const soon = await card("Скоро");
    expect(within(soon).getByTestId("expiry-badge")).toHaveTextContent(
      /Истекает через 5 дней/,
    );
    const healthy = await card("Здоров");
    expect(
      within(healthy).getByRole("button", { name: "Заменить токен" }),
    ).not.toHaveClass("primary");
  });

  it("без проблемных токенов предупреждения нет", async () => {
    setup();
    renderSettings(<GitAccessSection />);
    await card(USED_PAT.label);
    expect(screen.queryByText(/требуют внимания|требует внимания/)).toBeNull();
  });

  it("английский язык: тексты переведены", async () => {
    const { i18n } = await import("@shared/lib/i18n");
    await i18n.changeLanguage("en");
    setup();
    renderSettings(<GitAccessSection />);
    expect(
      screen.getByRole("heading", { name: "Repository access" }),
    ).toBeInTheDocument();
    expect(await screen.findByText("Trusted servers")).toBeInTheDocument();
    expect(
      await screen.findByRole("region", { name: "Encryption" }),
    ).toBeInTheDocument();
    expect(await screen.findByText("Git servers")).toBeInTheDocument();
    expect(screen.queryByTestId("browser-login-card")).toBeNull();
    expect(screen.queryByText("Soon")).toBeNull();
    await i18n.changeLanguage("ru");
  });
});
