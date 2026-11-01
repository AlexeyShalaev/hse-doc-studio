import { useEffect, useState, type ReactNode } from "react";
import type {
  AdminJob,
  AdminQueueSummary,
  AdminQuotas,
  AdminRunner,
  AdminRunnerRotated,
  AdminRunnerSummary,
  AdminRunnerToken,
  AdminRunnerTokenCreated,
  AdminService,
  AdminStorage,
  AdminStorageOwnerRow,
} from "@entities/session";
import type { ListQueryState } from "@shared/lib";
import type { GalleryEntry, GalleryGroup } from "@shared/lib/stateGallery";
import {
  useOwnerListState,
  useQueueListState,
  useRunnerListState,
  useTokenListState,
  type ListView,
} from "../lib/lists";
import { ensureAdminOpsLocales } from "../lib/locales";
import { runnerStatus } from "../lib/runnerStatus";
import type { ViewStatus } from "../lib/viewStatus";
import { Quotas } from "./Quotas";
import { QuotasView } from "./QuotasView";
import { Queue } from "./Queue";
import { QueueView, type QueueViewProps } from "./QueueView";
import type { QueueFilter as QueueFilterName } from "../lib/lists";
import {
  CreateTokenDialog,
  CreateTokenForm,
  RotatedDialog,
  SecretWithCommand,
} from "./RunnerDialogs";
import { Runners } from "./Runners";
import { RunnersPage } from "./RunnersPage";
import { RunnersView, type RunnersViewProps } from "./RunnersView";
import { PersonalRunnersView } from "./PersonalRunnersView";
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
): AdminRunner => {
  const base: AdminRunner = {
    id,
    name,
    status: "offline",
    tags: ["compile", "office"],
    concurrency: 2,
    resource_class: "standard",
    version: "0.3.0",
    created_at: ago(86400 * 6),
    last_seen_at: seen === null ? null : ago(seen),
    paused: false,
    revoked: false,
    owner_kind: "instance",
    owner: null,
    host_kind: "cli",
    ai_endpoints: [],
    last_seen_ip: null,
    ...extra,
  };
  // Состояние строки считает сервер; здесь по тем же правилам.
  return { ...base, status: runnerStatus(base, NOW) };
};

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

/** Окно статического списка галереи: страницы есть, фильтров сервера нет. */
const staticList = <T, F extends string, S extends string>(
  state: ListQueryState<F, S>,
  items: readonly T[],
  extra: { status?: ViewStatus; failed?: boolean; total?: number } = {},
): ListView<T, F, S> => {
  const total = extra.total ?? items.length;
  return {
    status: extra.status ?? "ready",
    items: items.slice(state.offset, state.offset + state.pageSize),
    total,
    fetching: false,
    failed: extra.failed ?? false,
    state,
    pagination: {
      page: state.page,
      pageSize: state.pageSize,
      total,
      onPageChange: state.setPage,
      pageSizes: state.pageSizes,
      onPageSizeChange: state.setPageSize,
    },
    onRetry: noop,
  };
};

/** Счётчики раннеров, как их считает сервер. */
const countsOf = (runners: readonly AdminRunner[]): AdminRunnerSummary => {
  const by = (st: AdminRunner["status"]) =>
    runners.filter((r) => r.status === st).length;
  const versions = runners.filter((r) => !r.revoked).map((r) => r.version);
  const newest = [...versions].sort().reverse()[0] ?? null;
  return {
    online: by("online"),
    paused: by("paused"),
    stale: by("stale"),
    offline: by("offline"),
    revoked: by("revoked"),
    outdated: versions.filter((v) => newest !== null && v !== newest).length,
    newest_version: newest,
  };
};

type RunnersDemoProps = {
  runners?: AdminRunner[];
  tokens?: AdminRunnerToken[];
  status?: ViewStatus;
  tokensStatus?: ViewStatus;
  extra?: Partial<RunnersViewProps>;
};

const RunnersDemo = ({
  runners = RUNNERS,
  tokens = TOKENS,
  status = "ready",
  tokensStatus = "ready",
  extra = {},
}: RunnersDemoProps) => {
  const runnerState = useRunnerListState();
  const tokenState = useTokenListState();
  return (
    <RunnersView
      runners={staticList(runnerState, runners, {
        status,
        failed: status === "error",
      })}
      tokens={staticList(tokenState, tokens, {
        status: tokensStatus,
        failed: tokensStatus === "error",
      })}
      counts={status === "ready" ? countsOf(runners) : null}
      countsStatus={status}
      summary={status === "ready" ? SUMMARY : null}
      summaryStatus={status}
      now={NOW}
      onTogglePause={noop}
      onRotate={noop}
      onRevoke={noop}
      onCreateToken={noop}
      onRevokeToken={noop}
      {...extra}
    />
  );
};

const runnersView = (props: RunnersDemoProps = {}) => (
  <RunnersDemo {...props} />
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
    error: "artifact_invalid",
  }),
  job("j7", "office.convert", "timed_out", {
    runner_id: "rn2",
    runner_name: "runner-2",
    attempt: 2,
    error: "job_timeout",
  }),
  job("j8", "compile", "cancelled", { project_id: null, project_name: null }),
];

const SUMMARY: AdminQueueSummary = {
  queued: 2,
  running: 2,
  by_state: {
    queued: 2,
    running: 2,
    succeeded: 14,
    failed: 1,
    cancelled: 1,
    timed_out: 1,
  },
  oldest_queued_age_s: 215,
  wait_p50_s: 12,
  wait_p95_s: 80,
  classes: [
    { name: "interactive", queued: 2 },
    { name: "checks", queued: 0 },
  ],
};

type QueueDemoProps = Partial<Omit<QueueViewProps, "state" | "pagination">> & {
  hasMore?: boolean;
  /** Показать вид «по фильтру ничего не нашлось». */
  filteredBy?: readonly string[];
};

const QueueDemo = ({
  hasMore = false,
  filteredBy,
  jobs = JOBS,
  ...extra
}: QueueDemoProps) => {
  const listState = useQueueListState();
  const state: ListQueryState<QueueFilterName, never> = filteredBy
    ? {
        ...listState,
        filters: { ...listState.filters, state: filteredBy },
        filter: (name) =>
          name === "state" ? (filteredBy[0] ?? "") : listState.filter(name),
        isFiltered: true,
        searchOnly: "",
        activeFilterCount: 1,
      }
    : listState;
  return (
    <QueueView
      summaryStatus="ready"
      summary={SUMMARY}
      status="ready"
      jobs={jobs}
      state={state}
      pagination={{
        mode: "cursor",
        shown: jobs.length,
        hasMore,
        onLoadMore: noop,
        loading: false,
        totalEstimate: hasMore ? 15_230 : null,
      }}
      now={NOW}
      onOpen={noop}
      onCancel={noop}
      {...extra}
    />
  );
};

const queueView = (props: QueueDemoProps = {}) => <QueueDemo {...props} />;

const QUOTAS: AdminQuotas = {
  user_concurrent: 2,
  org_concurrent: 6,
  max_duration_s: 600,
};

const quotasView = (
  quotas: AdminQuotas,
  extra: Partial<Parameters<typeof QuotasView>[0]> = {},
) => <QuotasView status="ready" quotas={quotas} onSave={noop} {...extra} />;

const svc = (
  id: string,
  kind: AdminService["kind"],
  status: AdminService["status"],
  detail: string | null,
  counts: [number, number] | null = null,
): AdminService => ({
  id,
  kind,
  status,
  detail,
  online: counts?.[0] ?? null,
  total: counts?.[1] ?? null,
});

const HEALTHY: AdminService[] = [
  svc("database", "database", "ok", null),
  svc("s3", "storage", "ok", null),
  svc("languagetool", "languagetool", "ok", null),
  svc("onlyoffice", "onlyoffice", "ok", null),
  svc("runners", "runners", "ok", null, [4, 6]),
  svc("smtp", "smtp", "ok", null),
];

const BROKEN: AdminService[] = [
  svc("database", "database", "ok", null),
  svc("s3", "storage", "down", "timeout"),
  svc("languagetool", "languagetool", "down", "no_healthy_replica"),
  svc("onlyoffice", "onlyoffice", "unconfigured", null),
  svc("runners", "runners", "down", "no_online_runner", [0, 3]),
  svc("smtp", "smtp", "unconfigured", null),
];

const STORAGE: AdminStorage = {
  blob_count: 1840,
  blob_bytes: Math.round(2.1 * GIB),
  projects: 38,
  deleted_projects: 3,
  free_bytes: 86 * GIB,
  volume_total_bytes: 200 * GIB,
  computed_at: ago(40),
  owners: [
    { id: "u3", name: "Мария Келлер", projects: 12 },
    { id: "u4", name: "Иван Сидоров", projects: 9 },
    { id: "u2", name: "Пётр Орлов", projects: 6 },
    { id: "u1", name: "Анна Петрова", projects: 2 },
  ],
};

const OWNERS: AdminStorageOwnerRow[] = [
  {
    kind: "org",
    id: "kafedra-ii",
    name: "Кафедра ИИ",
    email: null,
    projects: 14,
    bytes: Math.round(1.2 * GIB),
  },
  ...STORAGE.owners.map((o, i): AdminStorageOwnerRow => ({
    kind: "user",
    id: o.id,
    name: o.name,
    email: `${["maria.keller", "ivan.sidorov", "petr.orlov", "anna.petrova"][i] ?? "user"}@example.org`,
    projects: o.projects,
    bytes: o.projects * 48 * 1024 ** 2,
  })),
];

const StorageDemo = ({
  status = "ready",
  storage = STORAGE,
  owners = OWNERS,
  onRetry,
}: {
  status?: ViewStatus;
  storage?: AdminStorage | null;
  owners?: AdminStorageOwnerRow[];
  onRetry?: () => void;
}) => {
  const state = useOwnerListState();
  return (
    <StorageView
      status={status}
      storage={storage}
      owners={staticList(state, owners)}
      now={NOW}
      {...(onRetry ? { onRetry } : {})}
    />
  );
};

const live = (scenario: string) => ({ scenario });

/** Операционные экраны админки: раннеры, очередь, квоты, сервисы, хранилище; живые разделы на демо-мире. */
const personalRunner = (
  id: string,
  name: string,
  owner: [string, string, string],
  extra: Partial<AdminRunner> = {},
): AdminRunner => ({
  id,
  name,
  status: "online",
  tags: ["pack", "tex"],
  concurrency: 1,
  resource_class: "standard",
  version: "0.3.0",
  created_at: new Date(NOW - 3 * 86400_000).toISOString(),
  last_seen_at: new Date(NOW - 8000).toISOString(),
  paused: false,
  revoked: false,
  owner_kind: "user",
  owner: { id: owner[0], name: owner[1], email: owner[2] },
  host_kind: "desktop",
  ai_endpoints: [],
  last_seen_ip: "203.0.113.7",
  ...extra,
});

const ANNA_P: [string, string, string] = [
  "u_01hx7k2m9c",
  "Анна Петрова",
  "anna.petrova@example.org",
];
const PERSONAL_RUNNERS: AdminRunner[] = [
  personalRunner("pr1", "MacBook Анны", ANNA_P, { ai_endpoints: ["ollama"] }),
  personalRunner("pr2", "Домашний сервер", ANNA_P, {
    host_kind: "cli",
    paused: true,
    ai_endpoints: ["vllm"],
  }),
  personalRunner(
    "pr3",
    "gpu-box",
    ["u_01hx7k8maria", "Мария Келлер", "maria.keller@example.org"],
    {
      host_kind: "cli",
      version: "0.1.4",
      ai_endpoints: ["vllm", "ollama"],
      last_seen_at: new Date(NOW - 3 * 3600_000).toISOString(),
      last_seen_ip: null,
    },
  ),
];

const personalView = (
  extra: Partial<Parameters<typeof PersonalRunnersView>[0]> = {},
) => (
  <PersonalRunnersView
    status="ready"
    runners={PERSONAL_RUNNERS}
    enabled
    now={NOW}
    serverVersion="0.3.0"
    onTogglePause={noop}
    onRevoke={noop}
    {...extra}
  />
);

export const getAdminOpsGallery = (): GalleryGroup[] => [
  {
    id: "admin-ops-personal",
    title: "Админка: личные раннеры",
    description:
      "Машины людей: владелец, состояние, ИИ-адреса; пауза и отзыв без смены токена.",
    entries: [
      entry("admin_personal_list", "Личные раннеры в разных состояниях", () =>
        personalView(),
      ),
      entry("admin_personal_disabled", "Выключены в настройках сборки", () =>
        personalView({
          enabled: false,
          runners: PERSONAL_RUNNERS.map((r) => ({ ...r, status: "disabled" })),
        }),
      ),
      entry("admin_personal_empty", "Личных раннеров нет", () =>
        personalView({ runners: [] }),
      ),
      entry("admin_personal_loading", "Загрузка", () =>
        personalView({ status: "loading" }),
      ),
      entry("admin_personal_error", "Не загрузилось", () =>
        personalView({ status: "error", onRetry: noop }),
      ),
      entry(
        "admin_personal_live",
        "Живой раздел: раннеры и очередь с личными задачами",
        () => <RunnersPage />,
        live("admin_personal_runners"),
      ),
      entry(
        "admin_personal_live_off",
        "Живой раздел: личные раннеры выключены",
        () => <RunnersPage />,
        live("admin_runners_disabled"),
      ),
    ],
  },
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
        }),
      ),
      entry("admin_runners_busy", "Меняется раннер", () =>
        runnersView({ extra: { busyId: "rn1" } }),
      ),
      entry("admin_runners_forbidden", "Нет прав", () =>
        runnersView({
          status: "forbidden",
          runners: [],
          tokensStatus: "forbidden",
          tokens: [],
        }),
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
            by_state: {
              queued: 0,
              running: 0,
              succeeded: 0,
              failed: 0,
              cancelled: 0,
              timed_out: 0,
            },
            oldest_queued_age_s: null,
            wait_p50_s: null,
            wait_p95_s: null,
            classes: [],
          },
          jobs: [],
          hasMore: false,
        }),
      ),
      entry("admin_queue_forbidden", "Нет прав", () =>
        queueView({
          summaryStatus: "forbidden",
          summary: null,
          status: "forbidden",
          jobs: [],
        }),
      ),
      entry("admin_queue_nomatch", "Фильтр ничего не нашёл", () =>
        queueView({
          jobs: [],
          filteredBy: ["failed"],
        }),
      ),
      entry("admin_queue_more", "Есть ещё страницы", () =>
        queueView({ hasMore: true }),
      ),
      entry("admin_queue_loading", "Загрузка", () =>
        queueView({
          summaryStatus: "loading",
          summary: null,
          status: "loading",
          jobs: [],
          hasMore: false,
        }),
      ),
      entry("admin_queue_error", "Не загрузилась", () =>
        queueView({
          summaryStatus: "error",
          summary: null,
          status: "error",
          jobs: [],
          hasMore: false,
          onRetry: noop,
        }),
      ),
    ],
  },
  {
    id: "admin-ops-quotas",
    title: "Админка: квоты",
    entries: [
      entry("admin_quotas", "Три предела", () => quotasView(QUOTAS)),
      entry("admin_quotas_unlimited", "Без пределов", () =>
        quotasView({
          user_concurrent: null,
          org_concurrent: null,
          max_duration_s: null,
        }),
      ),
      entry("admin_quotas_failed", "Отказ сохранения", () =>
        quotasView(QUOTAS, { failure: { code: "input_invalid" } }),
      ),
      entry("admin_quotas_loading", "Загрузка", () =>
        quotasView(QUOTAS, { status: "loading", quotas: null }),
      ),
      entry("admin_quotas_error", "Не загрузились", () =>
        quotasView(QUOTAS, { status: "error", quotas: null, onRetry: noop }),
      ),
      entry("admin_quotas_forbidden", "Нет прав", () =>
        quotasView(QUOTAS, { status: "forbidden", quotas: null }),
      ),
    ],
  },
  {
    id: "admin-ops-services",
    title: "Админка: сервисы",
    entries: [
      entry("admin_services", "Всё работает", () => (
        <ServicesView status="ready" services={HEALTHY} onRefresh={noop} />
      )),
      entry("admin_services_broken", "Перебои и отказы", () => (
        <ServicesView status="ready" services={BROKEN} onRefresh={noop} />
      )),
      entry("admin_services_checking", "Идёт проверка", () => (
        <ServicesView
          status="ready"
          services={HEALTHY}
          refreshing
          onRefresh={noop}
        />
      )),
      entry("admin_services_loading", "Загрузка", () => (
        <ServicesView status="loading" services={[]} onRefresh={noop} />
      )),
      entry("admin_services_error", "Не загрузились", () => (
        <ServicesView
          status="error"
          services={[]}
          onRetry={noop}
          onRefresh={noop}
        />
      )),
      entry("admin_services_forbidden", "Нет прав", () => (
        <ServicesView status="forbidden" services={[]} onRefresh={noop} />
      )),
    ],
  },
  {
    id: "admin-ops-storage",
    title: "Админка: хранилище",
    entries: [
      entry("admin_storage", "Место занято", () => <StorageDemo />),
      entry("admin_storage_low", "Свободного места мало", () => (
        <StorageDemo
          storage={{ ...STORAGE, free_bytes: Math.round(2.4 * GIB) }}
        />
      )),
      entry("admin_storage_unknown", "Свободное место неизвестно", () => (
        <StorageDemo storage={{ ...STORAGE, free_bytes: null }} />
      )),
      entry("admin_storage_empty", "Проектов нет", () => (
        <StorageDemo
          owners={[]}
          storage={{
            ...STORAGE,
            blob_count: 0,
            blob_bytes: 0,
            projects: 0,
            deleted_projects: 0,
            owners: [],
          }}
        />
      )),
      entry("admin_storage_loading", "Загрузка", () => (
        <StorageDemo status="loading" storage={null} />
      )),
      entry("admin_storage_error", "Не загрузилось", () => (
        <StorageDemo status="error" storage={null} onRetry={noop} />
      )),
      entry("admin_storage_forbidden", "Нет прав", () => (
        <StorageDemo status="forbidden" storage={null} />
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
        () => <Runners creating={false} onCreatingChange={noop} />,
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
