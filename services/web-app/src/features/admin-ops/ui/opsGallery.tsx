import { useEffect, useState, type ReactNode } from "react";
import type {
  AdminJob,
  AdminQueueSummary,
  AdminQuotas,
  AdminRunner,
  AdminRunnerRotated,
  AdminRunnerToken,
  AdminRunnerTokenCreated,
  AdminService,
  AdminStorage,
} from "@entities/session";
import type { GalleryEntry, GalleryGroup } from "@shared/lib/stateGallery";
import { ensureAdminOpsLocales } from "../lib/locales";
import { Quotas } from "./Quotas";
import { QuotasView } from "./QuotasView";
import { Queue } from "./Queue";
import { QueueView, type QueueViewProps } from "./QueueView";
import {
  CreateTokenDialog,
  CreateTokenForm,
  RotatedDialog,
  SecretWithCommand,
} from "./RunnerDialogs";
import { Runners } from "./Runners";
import { RunnersPage } from "./RunnersPage";
import { RunnersView, type RunnersViewProps } from "./RunnersView";
import { Services } from "./Services";
import { ServicesView } from "./ServicesView";
import { Storage } from "./Storage";
import { StorageView } from "./StorageView";

const W = 900;
const noop = () => undefined;
const NOW = Date.parse("2026-10-27T10:00:00Z");
const ago = (s: number) => new Date(NOW - s * 1000).toISOString();
const GIB = 1024 ** 3;

/** Словарь загружается вместе с чанком админки; галерея ждёт его сама. */
const Ready = ({ children }: { children: ReactNode }) => {
  const [ready, setReady] = useState(false);
  useEffect(() => {
    let live = true;
    void ensureAdminOpsLocales().then(() => {
      if (live) setReady(true);
    });
    return () => {
      live = false;
    };
  }, []);
  return ready ? <>{children}</> : null;
};

const entry = (
  id: string,
  title: string,
  render: () => ReactNode,
  extra: Partial<GalleryEntry> = {},
): GalleryEntry => ({
  id,
  title,
  frame: "window",
  width: W,
  render: () => <Ready>{render()}</Ready>,
  ...extra,
});

const runner = (
  id: string,
  name: string,
  seen: number | null,
  extra: Partial<AdminRunner> = {},
): AdminRunner => ({
  id,
  name,
  tags: ["compile", "office"],
  concurrency: 2,
  resource_class: "standard",
  version: "0.3.0",
  created_at: ago(86400 * 6),
  last_seen_at: seen === null ? null : ago(seen),
  paused: false,
  revoked: false,
  ...extra,
});

const RUNNER_1 = runner("rn1", "runner-1", 6);
const RUNNERS: AdminRunner[] = [
  RUNNER_1,
  runner("rn2", "runner-2", 22, {
    concurrency: 4,
    tags: ["compile", "verify"],
  }),
  runner("rn3", "runner-3", 140, { version: "0.2.4" }),
  runner("rn4", "runner-4", 30, { paused: true }),
  runner("rn5", "runner-5", 7200),
  runner("rn6", "runner-6", null, { revoked: true }),
];

const token = (
  id: string,
  label: string,
  extra: Partial<AdminRunnerToken> = {},
): AdminRunnerToken => ({
  id,
  label,
  created_at: ago(3600),
  expires_at: new Date(NOW + 23 * 3600_000).toISOString(),
  max_uses: 1,
  uses: 0,
  revoked: false,
  ...extra,
});

const TOKENS: AdminRunnerToken[] = [
  token("t1", "Сервер в аудитории 305"),
  token("t2", "Запасной", { max_uses: 5, uses: 2 }),
  token("t3", "Тестовый стенд", { expires_at: ago(3600) }),
  token("t4", "", { uses: 1, max_uses: 1 }),
  token("t5", "Старый", { revoked: true }),
];

const COMMAND =
  "HSE_RUNNER__API_URL=https://studio.example.org HSE_RUNNER__TOKEN=hse_rt_3f9a1c7e5b2d4a60 hse-doc-studio runner";

const CREATED: AdminRunnerTokenCreated = {
  token: token("t9", "Сервер в аудитории 305"),
  secret: "hse_rt_3f9a1c7e5b2d4a60",
  command: COMMAND,
};

const ROTATED: AdminRunnerRotated = {
  runner: RUNNER_1,
  runner_token: "hse_rn_8d2e6b4f1a9c3075",
  command: COMMAND.replace(
    "hse_rt_3f9a1c7e5b2d4a60",
    "hse_rn_8d2e6b4f1a9c3075",
  ),
};

const runnersView = (extra: Partial<RunnersViewProps> = {}) => (
  <RunnersView
    status="ready"
    runners={RUNNERS}
    tokensStatus="ready"
    tokens={TOKENS}
    now={NOW}
    onTogglePause={noop}
    onRotate={noop}
    onRevoke={noop}
    onCreateToken={noop}
    onRevokeToken={noop}
    {...extra}
  />
);

const job = (
  id: string,
  kind: string,
  status: AdminJob["status"],
  extra: Partial<AdminJob> = {},
): AdminJob => ({
  id,
  kind,
  status,
  priority: kind === "compile" ? "interactive" : "checks",
  project_id: "p1",
  project_name: "Bertie: курсовая",
  user_id: "u1",
  user_name: "Анна Петрова",
  tags: [kind === "compile" ? "compile" : "office"],
  runner_id: null,
  runner_name: null,
  attempt: status === "queued" ? 0 : 1,
  max_attempts: 3,
  created_at: ago(60),
  started_at: status === "queued" ? null : ago(40),
  finished_at: status === "queued" || status === "running" ? null : ago(20),
  wait_s: 12,
  error: null,
  ...extra,
});

const JOBS: AdminJob[] = [
  job("j1", "compile", "queued", {
    wait_s: 215,
    user_name: "Пётр Орлов",
    project_name: "Лаборатория: отчёт",
  }),
  job("j2", "compile", "queued", { wait_s: 21 }),
  job("j3", "compile", "running", {
    runner_id: "rn1",
    runner_name: "runner-1",
    wait_s: 4,
  }),
  job("j4", "office.convert", "running", {
    runner_id: "rn2",
    runner_name: "runner-2",
    user_name: "Ольга Белова",
  }),
  job("j5", "compile", "succeeded", {
    runner_id: "rn1",
    runner_name: "runner-1",
  }),
  job("j6", "pack.submission", "failed", {
    runner_id: "rn2",
    runner_name: "runner-2",
    priority: "batch",
    error: "Сборка завершилась с ошибкой LaTeX: undefined control sequence",
  }),
  job("j7", "office.convert", "timed_out", {
    runner_id: "rn2",
    runner_name: "runner-2",
    attempt: 2,
    error: "Превышено время выполнения: 180 с",
  }),
  job("j8", "compile", "cancelled", { project_id: null, project_name: null }),
];

const SUMMARY: AdminQueueSummary = {
  queued: 2,
  running: 2,
  oldest_queued_age_s: 215,
  wait_p50_s: 12,
  wait_p95_s: 80,
  tags: [
    { tag: "compile", queued: 2, running: 1, avg_wait_s: 18 },
    { tag: "office", queued: 0, running: 1, avg_wait_s: null },
  ],
};

const QUERY = { status: "", kind: "", q: "", limit: 25 } as const;

const queueView = (extra: Partial<QueueViewProps> = {}) => (
  <QueueView
    summaryStatus="ready"
    summary={SUMMARY}
    status="ready"
    jobs={JOBS}
    total={JOBS.length}
    query={QUERY}
    now={NOW}
    onQueryChange={noop}
    onLoadMore={noop}
    onOpen={noop}
    onCancel={noop}
    {...extra}
  />
);

const QUOTAS: AdminQuotas = {
  jobs_concurrent: 2,
  jobs_max_duration_s: 600,
  fields: {
    jobs_concurrent: { source: "default", locked: false },
    jobs_max_duration_s: { source: "default", locked: false },
  },
  overrides: [
    {
      org_slug: "msp-2025",
      org_name: "МСПИН 2025",
      jobs_concurrent: 4,
      jobs_max_duration_s: null,
    },
    {
      org_slug: "ai-lab",
      org_name: "Лаборатория ИИ",
      jobs_concurrent: null,
      jobs_max_duration_s: 1800,
    },
  ],
};

const quotasView = (
  quotas: AdminQuotas,
  extra: Partial<Parameters<typeof QuotasView>[0]> = {},
) => (
  <QuotasView
    status="ready"
    quotas={quotas}
    canAddOverride
    onSave={noop}
    onAddOverride={noop}
    onEditOverride={noop}
    onClearOverride={noop}
    {...extra}
  />
);

const svc = (
  id: string,
  kind: AdminService["kind"],
  status: AdminService["status"],
  latency: number | null,
  detail: string | null,
  replicas: AdminService["replicas"] = [],
): AdminService => ({
  id,
  kind,
  status,
  latency_ms: latency,
  detail,
  checked_at: ago(20),
  replicas,
});
const rep = (
  name: string,
  status: AdminService["status"],
  latency: number | null,
  used: number | null,
  total: number | null,
) => ({
  name,
  status,
  latency_ms: latency,
  slots_used: used,
  slots_total: total,
});

const HEALTHY: AdminService[] = [
  svc("database", "database", "ok", 3, null),
  svc("storage", "storage", "ok", 24, null),
  svc("languagetool", "languagetool", "ok", 110, null, [
    rep("lt-1", "ok", 105, 1, 4),
    rep("lt-2", "ok", 118, 0, 4),
  ]),
  svc("onlyoffice", "onlyoffice", "ok", 64, null, [
    rep("oo-1", "ok", 61, 5, 5),
    rep("oo-2", "ok", 67, 2, 5),
  ]),
  svc("runners", "runners", "ok", null, null),
  svc("smtp", "smtp", "ok", 180, null),
];

const BROKEN: AdminService[] = [
  svc("database", "database", "ok", 4, null),
  svc("storage", "storage", "down", null, "Хранилище не отвечает"),
  svc(
    "languagetool",
    "languagetool",
    "degraded",
    920,
    "Одна реплика не отвечает",
    [rep("lt-1", "ok", 340, 3, 4), rep("lt-2", "down", null, null, null)],
  ),
  svc("onlyoffice", "onlyoffice", "unconfigured", null, null),
  svc("runners", "runners", "down", null, "Ни один раннер не в сети"),
  svc("smtp", "smtp", "degraded", 2400, "Сервер почты отвечает медленно"),
];

const STORAGE: AdminStorage = {
  total_bytes: Math.round(5.2 * GIB),
  free_bytes: 86 * GIB,
  volume_bytes: Math.round(3.1 * GIB),
  object_bytes: Math.round(2.1 * GIB),
  computed_at: ago(40),
  owners: [
    {
      kind: "org",
      id: "msp-2025",
      name: "МСПИН 2025",
      bytes: Math.round(3.6 * GIB),
      projects: 31,
    },
    {
      kind: "user",
      id: "u1",
      name: "Анна Петрова",
      bytes: Math.round(0.8 * GIB),
      projects: 2,
    },
    {
      kind: "org",
      id: "ai-lab",
      name: "Лаборатория ИИ",
      bytes: Math.round(0.5 * GIB),
      projects: 4,
    },
    {
      kind: "user",
      id: "u2",
      name: "Пётр Орлов",
      bytes: Math.round(0.3 * GIB),
      projects: 1,
    },
  ],
};

const live = (scenario: string) => ({ scenario });

/** Операционные экраны админки: раннеры, очередь, квоты, сервисы, хранилище; живые разделы на демо-мире. */
export const getAdminOpsGallery = (): GalleryGroup[] => [
  {
    id: "admin-ops-runners",
    title: "Админка: раннеры",
    entries: [
      entry("admin_runners", "Все состояния раннеров", () => runnersView(), {
        note: "В сети, давно не слышно, на паузе, не в сети, отозван; токены в разных статусах.",
      }),
      entry("admin_runners_offline", "Ни одного в сети", () =>
        runnersView({
          runners: [
            runner("a", "runner-1", 5400),
            runner("b", "runner-2", null),
          ],
        }),
      ),
      entry("admin_runners_empty", "Раннеров и токенов нет", () =>
        runnersView({ runners: [], tokens: [] }),
      ),
      entry("admin_runners_loading", "Загрузка", () =>
        runnersView({
          status: "loading",
          runners: [],
          tokensStatus: "loading",
          tokens: [],
        }),
      ),
      entry("admin_runners_error", "Не загрузились", () =>
        runnersView({
          status: "error",
          runners: [],
          tokensStatus: "error",
          tokens: [],
          onRetry: noop,
          onRetryTokens: noop,
        }),
      ),
      entry("admin_runners_busy", "Меняется раннер", () =>
        runnersView({ busyId: "rn1" }),
      ),
    ],
  },
  {
    id: "admin-ops-tokens",
    title: "Админка: токены и секреты",
    entries: [
      entry(
        "admin_token_form",
        "Форма токена регистрации",
        () => <CreateTokenForm onCancel={noop} onSubmit={noop} />,
        { width: 520 },
      ),
      entry(
        "admin_token_form_failed",
        "Отказ: слишком часто",
        () => (
          <CreateTokenForm
            failure={{ code: "rate_limited" }}
            onCancel={noop}
            onSubmit={noop}
          />
        ),
        { width: 520 },
      ),
      entry(
        "admin_token_secret",
        "Токен создан: секрет один раз",
        () => (
          <SecretWithCommand
            label="Токен регистрации"
            secret={CREATED.secret}
            command={CREATED.command}
            onClose={noop}
          />
        ),
        { width: 560, note: "Закрыть без копирования просит подтверждение." },
      ),
      entry(
        "admin_token_dialog",
        "Диалог создания",
        () => (
          <CreateTokenDialog
            isOpen
            pending={false}
            failure={null}
            created={null}
            onSubmit={noop}
            onClose={noop}
          />
        ),
        { frame: "plain" },
      ),
      entry(
        "admin_runner_rotated",
        "Новый токен раннера",
        () => <RotatedDialog rotated={ROTATED} onClose={noop} />,
        { frame: "plain" },
      ),
    ],
  },
  {
    id: "admin-ops-queue",
    title: "Админка: очередь",
    entries: [
      entry("admin_queue", "Очередь в работе", () => queueView(), {
        note: "Подсвечена задача, которая ждёт дольше двух минут.",
      }),
      entry("admin_queue_empty", "Очередь пуста", () =>
        queueView({
          summary: {
            queued: 0,
            running: 0,
            oldest_queued_age_s: null,
            wait_p50_s: null,
            wait_p95_s: null,
            tags: [],
          },
          jobs: [],
          total: 0,
        }),
      ),
      entry("admin_queue_nomatch", "Фильтр ничего не нашёл", () =>
        queueView({
          jobs: [],
          total: 0,
          query: { ...QUERY, status: "failed", q: "иванов" },
        }),
      ),
      entry("admin_queue_more", "Есть ещё страницы", () =>
        queueView({ total: 140 }),
      ),
      entry("admin_queue_loading", "Загрузка", () =>
        queueView({
          summaryStatus: "loading",
          summary: null,
          status: "loading",
          jobs: [],
          total: 0,
        }),
      ),
      entry("admin_queue_error", "Не загрузилась", () =>
        queueView({
          summaryStatus: "error",
          summary: null,
          status: "error",
          jobs: [],
          total: 0,
          onRetry: noop,
        }),
      ),
    ],
  },
  {
    id: "admin-ops-quotas",
    title: "Админка: квоты",
    entries: [
      entry("admin_quotas", "Значения и переопределения", () =>
        quotasView(QUOTAS),
      ),
      entry("admin_quotas_locked", "Предел времени задан окружением", () =>
        quotasView({
          ...QUOTAS,
          fields: {
            ...QUOTAS.fields,
            jobs_max_duration_s: { source: "env", locked: true },
          },
        }),
      ),
      entry("admin_quotas_empty", "Переопределений нет", () =>
        quotasView({ ...QUOTAS, overrides: [] }),
      ),
      entry("admin_quotas_failed", "Отказ сохранения", () =>
        quotasView(QUOTAS, { failure: { code: "setting_locked" } }),
      ),
      entry("admin_quotas_loading", "Загрузка", () =>
        quotasView(QUOTAS, { status: "loading", quotas: null }),
      ),
      entry("admin_quotas_error", "Не загрузились", () =>
        quotasView(QUOTAS, { status: "error", quotas: null, onRetry: noop }),
      ),
    ],
  },
  {
    id: "admin-ops-services",
    title: "Админка: сервисы",
    entries: [
      entry(
        "admin_services",
        "Всё работает",
        () => (
          <ServicesView
            status="ready"
            services={HEALTHY}
            now={NOW}
            onCheck={noop}
          />
        ),
        { note: "У ONLYOFFICE одна реплика занята полностью." },
      ),
      entry("admin_services_broken", "Перебои и отказы", () => (
        <ServicesView
          status="ready"
          services={BROKEN}
          now={NOW}
          onCheck={noop}
        />
      )),
      entry("admin_services_checking", "Идёт проверка", () => (
        <ServicesView
          status="ready"
          services={HEALTHY}
          now={NOW}
          checkingId="storage"
          onCheck={noop}
        />
      )),
      entry("admin_services_loading", "Загрузка", () => (
        <ServicesView status="loading" services={[]} now={NOW} onCheck={noop} />
      )),
      entry("admin_services_error", "Не загрузились", () => (
        <ServicesView
          status="error"
          services={[]}
          now={NOW}
          onRetry={noop}
          onCheck={noop}
        />
      )),
    ],
  },
  {
    id: "admin-ops-storage",
    title: "Админка: хранилище",
    entries: [
      entry("admin_storage", "Место занято", () => (
        <StorageView status="ready" storage={STORAGE} now={NOW} />
      )),
      entry("admin_storage_low", "Свободного места мало", () => (
        <StorageView
          status="ready"
          storage={{ ...STORAGE, free_bytes: Math.round(2.4 * GIB) }}
          now={NOW}
        />
      )),
      entry("admin_storage_unknown", "Свободное место неизвестно", () => (
        <StorageView
          status="ready"
          storage={{ ...STORAGE, free_bytes: null }}
          now={NOW}
        />
      )),
      entry("admin_storage_empty", "Проектов нет", () => (
        <StorageView
          status="ready"
          storage={{
            ...STORAGE,
            total_bytes: 0,
            volume_bytes: 0,
            object_bytes: 0,
            owners: [],
          }}
          now={NOW}
        />
      )),
      entry("admin_storage_loading", "Загрузка", () => (
        <StorageView status="loading" storage={null} now={NOW} />
      )),
      entry("admin_storage_error", "Не загрузилось", () => (
        <StorageView status="error" storage={null} now={NOW} onRetry={noop} />
      )),
    ],
  },
  {
    id: "admin-ops-live",
    title: "Админка: операционные разделы, живые",
    description:
      "На демо-мире. Имя токена, начинающееся с limit, даёт отказ по частоте. Завершённую задачу отменить нельзя. Три сценария меняют все разделы сразу: раннеры не в сети, сервисы падают, чистая установка.",
    entries: [
      entry(
        "admin_ops_runners",
        "Раннеры и очередь",
        () => <RunnersPage />,
        live("admin_ready"),
      ),
      entry(
        "admin_ops_runners_only",
        "Только раннеры",
        () => <Runners />,
        live("admin_ready"),
      ),
      entry(
        "admin_ops_queue",
        "Только очередь",
        () => <Queue />,
        live("admin_ready"),
      ),
      entry(
        "admin_ops_runners_offline",
        "Раннеры не в сети",
        () => <RunnersPage initialTab="queue" />,
        live("ops_runners_offline"),
      ),
      entry(
        "admin_ops_fresh",
        "Чистая установка: раннеры",
        () => <RunnersPage />,
        live("ops_fresh"),
      ),
      entry("admin_ops_quotas", "Квоты", () => <Quotas />, live("admin_ready")),
      entry(
        "admin_ops_services",
        "Сервисы",
        () => <Services />,
        live("admin_ready"),
      ),
      entry(
        "admin_ops_services_broken",
        "Сервисы падают",
        () => <Services />,
        live("ops_services_degraded"),
      ),
      entry(
        "admin_ops_storage",
        "Хранилище",
        () => <Storage />,
        live("admin_ready"),
      ),
      entry(
        "admin_ops_storage_low",
        "Хранилище: места мало",
        () => <Storage />,
        live("ops_services_degraded"),
      ),
    ],
  },
];
