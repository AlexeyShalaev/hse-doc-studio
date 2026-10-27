import { cleanup, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@shared/api";
import { i18n } from "@shared/lib/i18n";
import { settingsApi, type SettingsData } from "@entities/app-settings";
import {
  gitRemoteApi,
  type GitCredential,
  type GitCredentialCheck,
  type GitHostSettings,
} from "@entities/git-remote";
import { CHECK_OK, PAT, SSH_KEY } from "../testing/connectFixtures";
import {
  installPointerPolyfills,
  renderSettings,
  resetSettingsEnvironment,
} from "../testing/renderSettings";
import { GitAccessSection } from "./GitAccessSection";

const DAY = 24 * 3600 * 1000;
const inDays = (days: number): string =>
  new Date(Date.now() + days * DAY).toISOString();

const hostSettings = (over: Partial<GitHostSettings>): GitHostSettings => ({
  host: "gitlab.hse.local",
  port: null,
  provider_override: null,
  provider_info: { id: "gitlab", detected_by: "host", version: "17.3.1" },
  ca_present: false,
  pinned_fingerprint: null,
  ...over,
});

const gitlabToken = (over: Partial<GitCredential>): GitCredential => ({
  ...PAT,
  id: "cred-gl",
  label: "GitLab ВШЭ",
  host: "gitlab.hse.local",
  status: "ok",
  token_family: "glpat",
  expires_at: inDays(90),
  ...over,
});

const PEM = "-----BEGIN CERTIFICATE-----\nMIIBdemo\n-----END CERTIFICATE-----";

type Setup = {
  credentials?: GitCredential[];
  servers?: GitHostSettings[];
};

const setup = ({ credentials = [], servers = [] }: Setup = {}) => {
  vi.spyOn(gitRemoteApi, "listCredentials").mockResolvedValue(credentials);
  vi.spyOn(gitRemoteApi, "listHosts").mockResolvedValue([]);
  vi.spyOn(gitRemoteApi, "listHostSettings").mockResolvedValue(servers);
  vi.spyOn(gitRemoteApi, "getSecretsStatus").mockResolvedValue({
    ok: true,
    source: "file",
    permissions_enforced: true,
    credentials_total: credentials.length,
    credentials_unreadable: 0,
    data_dir_shared_folder: null,
  });
  vi.spyOn(settingsApi, "get").mockResolvedValue({
    git_fetch_interval_s: 300,
  } as unknown as SettingsData);
  return {
    check: vi
      .spyOn(gitRemoteApi, "checkCredential")
      .mockResolvedValue(CHECK_OK),
    update: vi
      .spyOn(gitRemoteApi, "updateHostSettings")
      .mockResolvedValue(hostSettings({})),
  };
};

const servers = async (): Promise<HTMLElement> => {
  const list = await screen.findByTestId("servers-list");
  return list;
};

const rowOf = async (host: string): Promise<HTMLElement> => {
  const rows = within(await servers()).getAllByTestId("server-row");
  const row = rows.find((item) => item.textContent.includes(host));
  if (!row) throw new Error(`нет строки ${host}`);
  return row;
};

describe("раздел «Доступ к репозиториям»: серверы git", () => {
  beforeEach(async () => {
    await resetSettingsEnvironment();
    installPointerPolyfills();
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("пустой список: пояснение и кнопка добавления", async () => {
    setup();
    renderSettings(<GitAccessSection />);
    expect(await screen.findByText("Серверы git")).toBeInTheDocument();
    expect(await screen.findByText(/Серверов пока нет/)).toBeInTheDocument();
    expect(screen.getByTestId("server-add")).toBeInTheDocument();
  });

  it("строка сервера: тип с версией, как определён, свой CA, закрепление, доступы", async () => {
    setup({
      servers: [
        hostSettings({ ca_present: true, port: 8443 }),
        hostSettings({
          host: "gitlab.lab.local",
          provider_info: { id: "gitlab", detected_by: "host", version: null },
          pinned_fingerprint: "SHA256:abc",
        }),
        hostSettings({
          host: "git.corp.example",
          provider_info: { id: "other", detected_by: "unknown", version: null },
        }),
      ],
      credentials: [gitlabToken({ expires_at: inDays(5) })],
    });
    renderSettings(<GitAccessSection />);
    const hse = await rowOf("gitlab.hse.local:8443");
    expect(within(hse).getByTestId("server-provider")).toHaveTextContent(
      "GitLab · v17.3",
    );
    expect(hse).toHaveTextContent("Тип определён по адресу");
    expect(within(hse).getByTestId("server-ca")).toHaveTextContent(
      "Свой сертификат CA",
    );
    const lab = await rowOf("gitlab.lab.local");
    expect(within(lab).getByTestId("server-pin")).toHaveTextContent(
      "Сертификат закреплён",
    );
    const other = await rowOf("git.corp.example");
    expect(other).toHaveTextContent("Другой сервер");
    expect(other).toHaveTextContent("Тип не определён");
  });

  it("хост с токеном, но без настроек, тоже в списке; скорый срок виден плашкой", async () => {
    setup({
      credentials: [
        gitlabToken({ host: "gitlab.hse.ru", expires_at: inDays(5) }),
      ],
    });
    renderSettings(<GitAccessSection />);
    const row = await rowOf("gitlab.hse.ru");
    expect(row).toHaveTextContent("1 доступ");
    expect(within(row).getByTestId("expiry-badge")).toHaveTextContent(
      "Истекает через 5 дней",
    );
    // Доступы сервера видны списком вместе со сроком каждого.
    expect(
      within(within(row).getByTestId("server-credentials")).getAllByRole(
        "listitem",
      ),
    ).toHaveLength(1);
  });

  it("настройка сервера: тип, добавление CA и снятие закрепления уходят одним запросом", async () => {
    const { update } = setup({
      servers: [
        hostSettings({
          provider_override: "gitlab",
          pinned_fingerprint: "SHA256:abc",
        }),
      ],
    });
    renderSettings(<GitAccessSection />);
    const user = userEvent.setup();
    const row = await rowOf("gitlab.hse.local");
    await user.click(
      within(row).getByRole("button", { name: /Настроить сервер/ }),
    );
    const dialog = await screen.findByRole("dialog", {
      name: "Сервер gitlab.hse.local",
    });
    expect(screen.getByTestId("host-settings-save")).toBeDisabled();
    await user.click(within(dialog).getByLabelText("Gitea"));
    await user.click(screen.getByTestId("host-ca-text"));
    await user.paste(PEM);
    await user.click(
      within(dialog).getByRole("button", { name: "Снять закрепление" }),
    );
    await user.click(screen.getByTestId("host-settings-save"));
    await waitFor(() => {
      expect(update).toHaveBeenCalledWith({
        host: "gitlab.hse.local",
        port: null,
        provider_override: "gitea",
        ca_pem: PEM,
        pinned_fingerprint: null,
      });
    });
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).toBeNull();
    });
  });

  it("свой CA можно убрать, автоопределение вернуть", async () => {
    const { update } = setup({
      servers: [hostSettings({ provider_override: "gitea", ca_present: true })],
    });
    renderSettings(<GitAccessSection />);
    const user = userEvent.setup();
    const row = await rowOf("gitlab.hse.local");
    await user.click(
      within(row).getByRole("button", { name: /Настроить сервер/ }),
    );
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Свой сертификат CA")).toBeInTheDocument();
    await user.click(
      within(dialog).getByRole("button", { name: "Удалить сертификат" }),
    );
    expect(
      within(dialog).getByText(/Сертификат будет удалён/),
    ).toBeInTheDocument();
    await user.click(within(dialog).getByLabelText("Определять автоматически"));
    await user.click(screen.getByTestId("host-settings-save"));
    await waitFor(() => {
      expect(update).toHaveBeenCalledWith({
        host: "gitlab.hse.local",
        port: null,
        provider_override: null,
        ca_pem: null,
      });
    });
  });

  it("настройки можно удалить целиком", async () => {
    const { update } = setup({
      servers: [hostSettings({ port: 8443, ca_present: true })],
    });
    renderSettings(<GitAccessSection />);
    const user = userEvent.setup();
    const row = await rowOf("gitlab.hse.local");
    await user.click(
      within(row).getByRole("button", { name: /Настроить сервер/ }),
    );
    await user.click(await screen.findByTestId("host-settings-remove"));
    await waitFor(() => {
      expect(update).toHaveBeenCalledWith({
        host: "gitlab.hse.local",
        port: 8443,
        provider_override: null,
        ca_pem: null,
        pinned_fingerprint: null,
      });
    });
  });

  it("новый сервер: адрес разбирается из ссылки, закрытый ключ не принимается", async () => {
    const { update } = setup();
    renderSettings(<GitAccessSection />);
    const user = userEvent.setup();
    await user.click(await screen.findByTestId("server-add"));
    const dialog = await screen.findByRole("dialog", {
      name: "Добавить сервер",
    });
    const save = screen.getByTestId("host-settings-save");
    expect(save).toBeDisabled();
    const host = within(dialog).getByLabelText("Адрес сервера");
    await user.type(host, "не адрес");
    await user.tab();
    expect(await screen.findByText(/Нужно имя сервера/)).toBeInTheDocument();
    expect(save).toBeDisabled();
    await user.clear(host);
    await user.type(host, "https://GitLab.HSE.local:8443/team");
    expect(save).toBeEnabled();

    await user.click(screen.getByTestId("host-ca-text"));
    await user.paste(
      "-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----",
    );
    expect(await screen.findByText(/Это закрытый ключ/)).toBeInTheDocument();
    expect(save).toBeDisabled();
    await user.clear(screen.getByTestId("host-ca-text"));
    await user.click(save);
    await waitFor(() => {
      expect(update).toHaveBeenCalledWith({
        host: "gitlab.hse.local",
        port: 8443,
      });
    });
  });

  it("отказ сервера показан в окне настроек", async () => {
    const { update } = setup({ servers: [hostSettings({})] });
    update.mockRejectedValue(new ApiError("нет", "git_error", 422));
    renderSettings(<GitAccessSection />);
    const user = userEvent.setup();
    const row = await rowOf("gitlab.hse.local");
    await user.click(
      within(row).getByRole("button", { name: /Настроить сервер/ }),
    );
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByLabelText("GitHub"));
    await user.click(screen.getByTestId("host-settings-save"));
    expect(await within(dialog).findByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("английский язык", async () => {
    await i18n.changeLanguage("en");
    setup({ servers: [hostSettings({ ca_present: true })] });
    renderSettings(<GitAccessSection />);
    const row = await rowOf("gitlab.hse.local");
    expect(within(row).getByTestId("server-ca")).toHaveTextContent(
      "Own CA certificate",
    );
    expect(screen.getByTestId("server-add")).toHaveTextContent("Add a server");
    await i18n.changeLanguage("ru");
  });
});

describe("раздел «Доступ к репозиториям»: сроки и проверка токенов", () => {
  beforeEach(async () => {
    await resetSettingsEnvironment();
    installPointerPolyfills();
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  const card = async (label: string): Promise<HTMLElement> => {
    // Подпись доступа есть и в карточке, и в списке сервера: нужна карточка.
    const titles = await screen.findAllByText(label);
    for (const title of titles) {
      const element = title.closest("[data-testid='credential-card']");
      if (element instanceof HTMLElement) return element;
    }
    throw new Error("нет карточки");
  };

  it("срок токена: далеко, скоро, просрочен, без срока", async () => {
    setup({
      credentials: [
        gitlabToken({ id: "a", label: "Далеко", expires_at: inDays(120) }),
        gitlabToken({ id: "b", label: "Скоро", expires_at: inDays(5) }),
        gitlabToken({
          id: "c",
          label: "Просрочен",
          expires_at: inDays(-3),
          status: "auth_failed",
        }),
        gitlabToken({ id: "d", label: "Без срока", expires_at: null }),
        { ...SSH_KEY, id: "e", label: "Ключ" },
      ],
    });
    renderSettings(<GitAccessSection />);
    expect(
      within(await card("Далеко")).getByTestId("expiry-badge"),
    ).toHaveTextContent("Действует до");
    expect(
      within(await card("Скоро")).getByTestId("expiry-badge"),
    ).toHaveAttribute("data-state", "soon");
    expect(
      within(await card("Скоро")).getByTestId("expiry-badge"),
    ).toHaveTextContent("Истекает через 5 дней");
    expect(
      within(await card("Просрочен")).getByTestId("expiry-badge"),
    ).toHaveTextContent("Истёк 3 дня назад");
    expect(
      within(await card("Без срока")).queryByTestId("expiry-badge"),
    ).toBeNull();
    expect(within(await card("Ключ")).queryByTestId("expiry-badge")).toBeNull();
    expect(
      within(await card("Ключ")).queryByTestId("credential-check"),
    ).toBeNull();
  });

  it("«Проверить»: показывает владельца, права и срок, статус доступа обновляется", async () => {
    const { check } = setup({
      credentials: [gitlabToken({ status: "unverified" })],
    });
    const result: GitCredentialCheck = {
      credential: gitlabToken({ status: "ok" }),
      provider_info: { id: "gitlab", detected_by: "host", version: "17.3.1" },
      token_info: {
        login: "anna.petrova",
        scopes: ["read_repository", "write_repository"],
        expires_at: inDays(40),
        sufficiency: "sufficient",
        missing: [],
      },
    };
    check.mockResolvedValue(result);
    renderSettings(<GitAccessSection />);
    const user = userEvent.setup();
    const item = await card("GitLab ВШЭ");
    await user.click(within(item).getByTestId("credential-check"));
    expect(
      await screen.findByTestId("token-check-sufficient"),
    ).toHaveTextContent("Токен подходит");
    expect(screen.getByTestId("token-facts")).toHaveTextContent("anna.petrova");
    expect(screen.getByTestId("token-facts")).toHaveTextContent("GitLab 17.3");
    expect(check).toHaveBeenCalledWith("cred-gl");
  });

  it("мало прав: сказано, что добавить, есть ссылка на новый токен", async () => {
    const { check } = setup({ credentials: [gitlabToken({})] });
    check.mockResolvedValue({
      credential: gitlabToken({}),
      provider_info: { id: "gitlab", detected_by: "host", version: null },
      token_info: {
        login: "anna",
        scopes: ["read_repository"],
        expires_at: null,
        sufficiency: "too_narrow",
        missing: ["write_repository"],
      },
    });
    renderSettings(<GitAccessSection />);
    const user = userEvent.setup();
    await user.click(
      within(await card("GitLab ВШЭ")).getByTestId("credential-check"),
    );
    expect(
      await screen.findByTestId("token-check-too_narrow"),
    ).toHaveTextContent("write_repository");
    expect(
      screen
        .getByRole("link", { name: /Создать новый токен/ })
        .getAttribute("href"),
    ).toContain("gitlab.hse.local/-/user_settings/personal_access_tokens");
  });

  it("сертификат: из карточки токена открывается окно и проверка повторяется", async () => {
    const { check, update } = setup({ credentials: [gitlabToken({})] });
    check.mockRejectedValueOnce(
      new ApiError("d", "tls_untrusted_ca", 502, {
        certificate: {
          fingerprint_sha256: "SHA256:abc",
          subject: "CN=gitlab.hse.local",
          issuer: "CN=HSE Internal CA",
          not_before: "2026-01-10T00:00:00Z",
          not_after: "2027-01-10T00:00:00Z",
          self_signed: false,
        },
      }),
    );
    renderSettings(<GitAccessSection />);
    const user = userEvent.setup();
    await user.click(
      within(await card("GitLab ВШЭ")).getByTestId("credential-check"),
    );
    await user.click(
      await screen.findByRole("button", { name: "Проверить сертификат" }),
    );
    await user.click(await screen.findByTestId("tls-ca-text"));
    await user.paste(PEM);
    await user.click(screen.getByTestId("tls-submit"));
    await waitFor(() => {
      expect(update).toHaveBeenCalledWith({
        host: "gitlab.hse.local",
        port: null,
        ca_pem: PEM,
      });
    });
    expect(
      await screen.findByTestId("token-check-sufficient"),
    ).toBeInTheDocument();
    expect(check).toHaveBeenCalledTimes(2);
  });

  it("запрос проверки упал: понятное сообщение и повтор", async () => {
    const { check } = setup({ credentials: [gitlabToken({})] });
    check.mockRejectedValueOnce(new ApiError("нет сети", "offline", 502));
    renderSettings(<GitAccessSection />);
    const user = userEvent.setup();
    await user.click(
      within(await card("GitLab ВШЭ")).getByTestId("credential-check"),
    );
    expect(await screen.findByTestId("token-check-offline")).toHaveTextContent(
      "Нет связи с сервером",
    );
    await user.click(screen.getByRole("button", { name: "Проверить ещё раз" }));
    expect(
      await screen.findByTestId("token-check-sufficient"),
    ).toBeInTheDocument();
  });
});
