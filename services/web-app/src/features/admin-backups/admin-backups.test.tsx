import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  cleanup,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { I18nextProvider } from "react-i18next";
import { MemoryRouter } from "react-router";
import {
  afterEach,
  beforeAll,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";
import { i18n } from "@shared/lib";
import { backupsApi } from "./api/backupsApi";
import type { BackupDestination, BackupRun, BackupStatus } from "./api/schemas";
import {
  bodyFromDraft,
  draftProblem,
  emptyDraft,
  OWN_S3_HINT,
  withOwnS3,
} from "./lib/destinationDraft";
import { ensureAdminBackupsLocales } from "./lib/locales";
import {
  cronProblem,
  settingsDraftOf,
  settingsFromDraft,
} from "./lib/settingsDraft";
import { BackupsPage } from "./ui/BackupsPage";

const NOW = "2026-11-01T12:00:00Z";

const dest = (patch: Partial<BackupDestination> = {}): BackupDestination => ({
  id: "d1",
  name: "Свой S3",
  kind: "s3",
  is_default: true,
  endpoint: "http://backup-minio:9000",
  region: "us-east-1",
  bucket: "hse-backups",
  prefix: "studio",
  path_style: true,
  local_path: null,
  access_key_hint: "…1234",
  secret_key_set: true,
  created_at: NOW,
  updated_at: NOW,
  last_check_at: null,
  last_check_ok: null,
  last_check_error: null,
  ...patch,
});

const run = (patch: Partial<BackupRun> = {}): BackupRun => ({
  id: "r1",
  destination_id: "d1",
  destination_name: "Свой S3",
  trigger: "manual",
  status: "ok",
  stage: null,
  started_at: NOW,
  finished_at: NOW,
  duration_s: 75,
  size_bytes: 2_236_042,
  backup_id: "20261101T110016Z-0b725f",
  error: null,
  removed_at: null,
  ...patch,
});

const status = (patch: Partial<BackupStatus> = {}): BackupStatus => ({
  settings: {
    enabled: true,
    schedule_kind: "cron",
    interval_hours: 24,
    cron: "0 3 * * *",
    keep_last: 7,
    keep_days: 30,
    encryption_mode: "installation",
    notify_admins: true,
    passphrase_set: false,
  },
  next_run_at: "2026-11-02T03:00:00Z",
  last_scheduled_at: null,
  running: null,
  last_run: run(),
  local_root: "/data/backups",
  destinations_total: 1,
  ...patch,
});

const wrap = (node: React.ReactNode) => (
  <I18nextProvider i18n={i18n}>
    <QueryClientProvider
      client={
        new QueryClient({
          defaultOptions: {
            queries: { retry: false },
            mutations: { retry: false },
          },
        })
      }
    >
      <MemoryRouter>{node}</MemoryRouter>
    </QueryClientProvider>
  </I18nextProvider>
);

describe("назначения: чистая логика формы", () => {
  it("свой S3 подставляет значения оверлея и не трогает ключи", () => {
    const filled = withOwnS3({
      ...emptyDraft(true),
      accessKey: "AK",
      secretKey: "SK",
    });
    expect(filled.endpoint).toBe(OWN_S3_HINT.endpoint);
    expect(filled.bucket).toBe("hse-backups");
    expect(filled.pathStyle).toBe(true);
    expect(filled.accessKey).toBe("AK");
    expect(draftProblem(filled, false)).toBeNull();
  });

  it("при создании ключи обязательны, при правке пустые значат «оставить»", () => {
    const base = { ...withOwnS3(emptyDraft(true)) };
    expect(draftProblem(base, false)).toBe("accessKey");
    expect(draftProblem({ ...base, accessKey: "A" }, false)).toBe("secretKey");
    expect(draftProblem(base, true)).toBeNull();
    const body = bodyFromDraft(base);
    expect(body.access_key).toBeNull();
    expect(body.secret_key).toBeNull();
  });

  it("неверные бакет, адрес, префикс и путь отвергаются", () => {
    const ok = {
      ...withOwnS3(emptyDraft(true)),
      accessKey: "A",
      secretKey: "S",
    };
    expect(draftProblem({ ...ok, bucket: "UP" }, false)).toBe("bucket");
    expect(draftProblem({ ...ok, endpoint: "ftp://x" }, false)).toBe(
      "endpoint",
    );
    expect(draftProblem({ ...ok, prefix: "a/../b" }, false)).toBe("prefix");
    expect(draftProblem({ ...ok, name: " " }, false)).toBe("name");
    const local = { ...emptyDraft(true), name: "Диск", kind: "local" as const };
    expect(draftProblem({ ...local, localPath: "../etc" }, false)).toBe(
      "localPath",
    );
    expect(draftProblem({ ...local, localPath: "" }, false)).toBe("localPath");
    expect(
      draftProblem({ ...local, localPath: "disk1/studio" }, false),
    ).toBeNull();
  });

  it("тело локального назначения не несёт полей S3", () => {
    const body = bodyFromDraft({
      ...emptyDraft(false),
      name: "Диск",
      kind: "local",
      localPath: "disk1",
      endpoint: "http://x",
    });
    expect(body).toMatchObject({
      kind: "local",
      local_path: "disk1",
      bucket: null,
      endpoint: null,
      access_key: null,
    });
  });
});

describe("расписание: чистая логика формы", () => {
  it("cron из пяти полей", () => {
    expect(cronProblem("0 3 * * *")).toBe(false);
    expect(cronProblem("*/15 9-10 * * 1,3")).toBe(false);
    expect(cronProblem("0 3 * *")).toBe(true);
    expect(cronProblem("61 * * * *")).toBe(true);
    expect(cronProblem("*/0 * * * *")).toBe(true);
  });

  it("границы хранения и фраза", () => {
    const draft = settingsDraftOf(status().settings);
    expect("body" in settingsFromDraft(draft, false)).toBe(true);
    expect(settingsFromDraft({ ...draft, keepLast: "-1" }, false)).toEqual({
      problem: "keep_last",
    });
    expect(settingsFromDraft({ ...draft, keepDays: "99999" }, false)).toEqual({
      problem: "keep_days",
    });
    expect(
      settingsFromDraft({ ...draft, scheduleKind: "cron", cron: "x" }, false),
    ).toEqual({ problem: "cron" });
    expect(
      settingsFromDraft(
        { ...draft, scheduleKind: "interval", intervalHours: "0" },
        false,
      ),
    ).toEqual({ problem: "interval_hours" });
    const phrase = { ...draft, encryptionMode: "passphrase" as const };
    expect(settingsFromDraft(phrase, false)).toEqual({ problem: "passphrase" });
    expect(settingsFromDraft({ ...phrase, passphrase: "short" }, true)).toEqual(
      { problem: "passphrase" },
    );
    const kept = settingsFromDraft(phrase, true);
    expect("body" in kept && kept.body.passphrase).toBeNull();
    const fresh = settingsFromDraft(
      { ...phrase, passphrase: "a long enough phrase" },
      false,
    );
    expect("body" in fresh && fresh.body.passphrase).toBe(
      "a long enough phrase",
    );
  });
});

describe("раздел «Бэкапы»", () => {
  beforeAll(async () => {
    await ensureAdminBackupsLocales();
    await i18n.changeLanguage("ru");
  });

  beforeEach(() => {
    vi.spyOn(backupsApi, "status").mockResolvedValue(status());
    vi.spyOn(backupsApi, "destinations").mockResolvedValue([dest()]);
    vi.spyOn(backupsApi, "runs").mockResolvedValue({
      items: [
        run(),
        run({
          id: "r2",
          status: "failed",
          error: "S3 недоступен",
          size_bytes: null,
          backup_id: null,
        }),
      ],
      total: 2,
      limit: 10,
      offset: 0,
    });
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("показывает назначение, историю с размером и ошибкой, секретов нет", async () => {
    render(wrap(<BackupsPage />));
    const row = await screen.findByTestId("backup-dest-d1");
    expect(within(row).getByText(/по умолчанию/)).toBeInTheDocument();
    expect(within(row).getByText(/…|hse-backups/)).toBeInTheDocument();
    const runs = await screen.findByTestId("backup-runs");
    expect(await within(runs).findByText("S3 недоступен")).toBeInTheDocument();
    expect(within(runs).getByText(/2,1 МБ|2\.1 MB|2,1/)).toBeInTheDocument();
    expect(document.body.textContent).not.toContain("secret");
  });

  it("без назначений предупреждает и блокирует запуск", async () => {
    vi.spyOn(backupsApi, "destinations").mockResolvedValue([]);
    vi.spyOn(backupsApi, "status").mockResolvedValue(
      status({ destinations_total: 0 }),
    );
    render(wrap(<BackupsPage />));
    expect(
      await screen.findByTestId("backup-banner-empty"),
    ).toBeInTheDocument();
    expect(screen.getByTestId("backup-run-now")).toBeDisabled();
  });

  it("идущий запуск виден баннером, кнопка запуска заблокирована", async () => {
    vi.spyOn(backupsApi, "status").mockResolvedValue(
      status({
        running: run({
          status: "running",
          stage: "files.tar.enc",
          finished_at: null,
        }),
      }),
    );
    render(wrap(<BackupsPage />));
    const banner = await screen.findByTestId("backup-banner-running");
    expect(banner.textContent).toContain("файлы");
    expect(screen.getByTestId("backup-run-now")).toBeDisabled();
  });

  it("последний сбой показан красным баннером с текстом ошибки", async () => {
    vi.spyOn(backupsApi, "status").mockResolvedValue(
      status({
        last_run: run({ status: "failed", error: "pg_dump exited with 1" }),
      }),
    );
    render(wrap(<BackupsPage />));
    const banner = await screen.findByTestId("backup-banner-failed");
    expect(banner.textContent).toContain("pg_dump exited with 1");
  });

  it("ручной запуск вызывает API с назначением по умолчанию", async () => {
    const start = vi
      .spyOn(backupsApi, "start")
      .mockResolvedValue(run({ status: "running" }));
    render(wrap(<BackupsPage />));
    const button = await screen.findByTestId("backup-run-now");
    await waitFor(() => expect(button).toBeEnabled());
    await userEvent.click(button);
    await waitFor(() => {
      expect(start).toHaveBeenCalledWith(null);
    });
  });

  it("создание: подсказка заполняет значения, проверка и сохранение уходят без чужих полей", async () => {
    const user = userEvent.setup();
    vi.spyOn(backupsApi, "destinations").mockResolvedValue([]);
    const test = vi.spyOn(backupsApi, "testForm").mockResolvedValue({
      ok: true,
      error: null,
      warnings: ["same_as_primary"],
      checked_at: NOW,
    });
    const create = vi
      .spyOn(backupsApi, "createDestination")
      .mockResolvedValue(dest());
    render(wrap(<BackupsPage />));
    await user.click(await screen.findByTestId("backup-add"));
    await screen.findByTestId("backup-dest-dialog");
    await user.click(screen.getByText(/Как подключить своё S3/));
    await user.click(screen.getByTestId("backup-hint-fill"));
    expect(screen.getByTestId("backup-dest-endpoint")).toHaveValue(
      "http://backup-minio:9000",
    );
    expect(screen.getByTestId("backup-dest-bucket")).toHaveValue("hse-backups");
    await user.click(screen.getByTestId("backup-dest-save"));
    expect(create).not.toHaveBeenCalled();
    await user.type(screen.getByTestId("backup-dest-access"), "studiobk");
    await user.type(screen.getByTestId("backup-dest-secret"), "s3cret-value");
    await user.click(screen.getByTestId("backup-dest-check"));
    const result = await screen.findByTestId("backup-dest-check-result");
    expect(result.textContent).toContain("Подключение работает");
    expect(result.textContent).toContain("то же хранилище");
    expect(test).toHaveBeenCalledOnce();
    await user.click(screen.getByTestId("backup-dest-save"));
    await waitFor(() => {
      expect(create).toHaveBeenCalledOnce();
    });
    expect(create.mock.calls[0]?.[0]).toMatchObject({
      kind: "s3",
      bucket: "hse-backups",
      access_key: "studiobk",
      secret_key: "s3cret-value",
      make_default: true,
    });
  });

  it("правка: ключи не подставляются, пустые поля не уходят", async () => {
    const user = userEvent.setup();
    const update = vi
      .spyOn(backupsApi, "updateDestination")
      .mockResolvedValue(dest({ name: "Новое имя" }));
    render(wrap(<BackupsPage />));
    await user.click(await screen.findByTestId("backup-dest-edit-d1"));
    expect(screen.getByTestId("backup-dest-access")).toHaveValue("");
    expect(screen.getByTestId("backup-dest-secret")).toHaveValue("");
    const name = screen.getByTestId("backup-dest-name");
    await user.clear(name);
    await user.type(name, "Новое имя");
    await user.click(screen.getByTestId("backup-dest-save"));
    await waitFor(() => {
      expect(update).toHaveBeenCalledOnce();
    });
    expect(update.mock.calls[0]?.[0]).toBe("d1");
    expect(update.mock.calls[0]?.[1]).toMatchObject({
      name: "Новое имя",
      access_key: null,
      secret_key: null,
    });
  });

  it("проверка сохранённого назначения показывает предупреждение", async () => {
    const user = userEvent.setup();
    vi.spyOn(backupsApi, "testSaved").mockResolvedValue({
      ok: true,
      error: null,
      warnings: ["same_as_primary"],
      checked_at: NOW,
    });
    render(wrap(<BackupsPage />));
    await user.click(await screen.findByTestId("backup-dest-test-d1"));
    expect(await screen.findByText(/то же хранилище/)).toBeInTheDocument();
  });

  it("список бэкапов в назначении: команда восстановления без секретов, удаление с подтверждением", async () => {
    const user = userEvent.setup();
    const stored = {
      backup_id: "20261101T110016Z-0b725f",
      created_at: NOW,
      app_version: "0.2.0",
      schema_revision: "bk_01_backups",
      installation_id: null,
      encryption_mode: "installation" as const,
      size: 2_236_042,
      parts: [],
      manifest_sha256: "a".repeat(64),
      restore_command:
        "hse-doc-studio backup restore --s3-bucket hse-backups --backup-id 20261101T110016Z-0b725f",
    };
    vi.spyOn(backupsApi, "stored").mockResolvedValue([stored]);
    const remove = vi.spyOn(backupsApi, "deleteStored").mockResolvedValue();
    render(wrap(<BackupsPage />));
    await user.click(await screen.findByTestId("backup-dest-open-d1"));
    const item = await screen.findByTestId(`backup-stored-${stored.backup_id}`);
    expect(item.textContent).toContain("backup restore --s3-bucket");
    await user.click(
      within(item).getByTestId(`backup-stored-delete-${stored.backup_id}`),
    );
    expect(remove).not.toHaveBeenCalled();
    await user.click(
      within(item).getByTestId(
        `backup-stored-delete-confirm-${stored.backup_id}`,
      ),
    );
    await waitFor(() => {
      expect(remove).toHaveBeenCalledWith("d1", stored.backup_id);
    });
  });

  it("настройки: неверный cron не уходит на сервер, верный сохраняется", async () => {
    const user = userEvent.setup();
    const save = vi
      .spyOn(backupsApi, "saveSettings")
      .mockResolvedValue(status());
    render(wrap(<BackupsPage />));
    const cron = await screen.findByTestId("backup-cron");
    await user.clear(cron);
    await user.type(cron, "bad");
    await user.click(screen.getByTestId("backup-settings-save"));
    expect(save).not.toHaveBeenCalled();
    expect(await screen.findByText(/пять полей cron/i)).toBeInTheDocument();
    await user.clear(cron);
    await user.type(cron, "30 2 * * 1");
    await user.click(screen.getByTestId("backup-settings-save"));
    await waitFor(() => {
      expect(save).toHaveBeenCalledOnce();
    });
    expect(save.mock.calls[0]?.[0]).toMatchObject({
      cron: "30 2 * * 1",
      keep_last: 7,
      passphrase: null,
    });
  });
});
