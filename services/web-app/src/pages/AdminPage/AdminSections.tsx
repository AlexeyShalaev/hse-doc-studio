import type { ReactNode } from "react";
import {
  Activity,
  CircleAlert,
  CircleCheck,
  Cpu,
  HardDrive,
  KeyRound,
  Mail,
  Server,
  SlidersHorizontal,
  TriangleAlert,
  UserPlus,
  Users,
} from "lucide-react";
import { Link } from "react-router";
import { useTranslation } from "react-i18next";
import { formatFileSize, formatPastTime, localeTag } from "@shared/lib";
import {
  AdminPage,
  Avatar,
  EmptyState,
  ErrorState,
  KpiGrid,
  KpiTile,
  ListRow,
  Section,
  SectionList,
  StatusDot,
  TableSkeleton,
  type StatusDotStatus,
} from "@shared/ui";
import {
  useBootstrap,
  type AdminAuditEvent,
  type AdminService,
} from "@entities/session";
import { useInstanceSettings } from "@features/admin-install";
import {
  diskTone,
  isLowSpace,
  liveRunners,
  quietRunners,
  summarizeHealth,
  useNow,
  useQueueSummary,
  useRunnerSummary,
  useServices,
  useStorage,
} from "@features/admin-ops";
import {
  auditTarget,
  isPseudonym,
  useApprovals,
  useAuditActionLabel,
  useRecentAudit,
  useUsers,
} from "@features/admin-users";

// Сводка установки: числа, то, что ждёт решения, последние действия и быстрые
// переходы. Каждый блок живёт своим запросом: упавший показывает ошибку у
// себя, остальная страница работает.

const ACTIVITY_LIMIT = 7;

const ALL_USERS = { q: "", status: "", page: 0 } as const;

type Tone = "warning" | "danger" | "info";

type Attention = {
  id: string;
  tone: Tone;
  title: string;
  body: string;
  to: string;
};

const TONE_ICON: Record<Tone, ReactNode> = {
  danger: <TriangleAlert size={15} />,
  warning: <CircleAlert size={15} />,
  info: <Mail size={15} />,
};

const isBad = (s: AdminService): boolean =>
  s.status === "degraded" || s.status === "down";

/** Число по правилам языка интерфейса. */
const useNumber = (): ((value: number) => string) => {
  const fmt = new Intl.NumberFormat(localeTag());
  return (value) => fmt.format(value);
};

// Ошибка только без данных: неудачный фоновый опрос не стирает прежнее значение плитки.
const failedEmpty = (q: { data: unknown; isError: boolean }) =>
  q.data === undefined && q.isError;

const Kpis = () => {
  const { t } = useTranslation("adminShell");
  const num = useNumber();
  const users = useUsers(ALL_USERS);
  const approvals = useApprovals(0);
  const runners = useRunnerSummary();
  const summary = useQueueSummary();
  const services = useServices();
  const storage = useStorage();

  const waiting = approvals.data?.total ?? 0;
  const counts = runners.data;
  const live = counts ? liveRunners(counts) : 0;
  const online = counts?.online ?? 0;
  // Как в «Требует внимания»: приостановленные молчат намеренно.
  const quiet = counts ? quietRunners(counts) : 0;
  // То же правило, что на странице «Сервисы»: мало раннеров в сети уже перебои.
  // Неподключённый сервис не сломан: его не считаем ни в норме, ни в сбое.
  const health = summarizeHealth(services.data ?? []);
  const okServices = health.ok.length;
  const offServices = health.off.length;
  const downServices = health.down.length;
  const warnServices = health.warn.length;
  const disk = storage.data;
  // Занятое место на диске проектов, как на странице «Хранилище»; без данных о
  // томе показываем объём сборок и вложений.
  const usedBytes =
    disk?.volume_total_bytes && disk.free_bytes !== null
      ? disk.volume_total_bytes - disk.free_bytes
      : null;
  const used =
    usedBytes !== null && disk?.volume_total_bytes
      ? (usedBytes / disk.volume_total_bytes) * 100
      : null;
  const storageTone = disk ? diskTone(disk) : "neutral";
  const failed = t("overview.kpi.failed");

  return (
    <KpiGrid>
      <KpiTile
        testId="overview-kpi-people"
        to="/admin/users"
        icon={<Users size={14} aria-hidden="true" />}
        label={t("overview.kpi.people")}
        loading={users.isPending && !users.isError}
        error={failedEmpty(users) ? failed : undefined}
        value={num(users.data?.total ?? 0)}
        tone={waiting > 0 ? "warning" : "neutral"}
        secondary={
          waiting > 0
            ? t("overview.kpi.peopleWaiting", { count: waiting })
            : t("overview.kpi.peopleNoWaiting")
        }
      />
      <KpiTile
        testId="overview-kpi-runners"
        to="/admin/runners"
        icon={<Server size={14} aria-hidden="true" />}
        label={t("overview.kpi.runners")}
        loading={runners.isPending && !runners.isError}
        error={failedEmpty(runners) ? failed : undefined}
        value={num(online)}
        unit={
          live > 0
            ? t("overview.kpi.runnersOf", { total: num(live) })
            : undefined
        }
        tone={
          live === 0
            ? "neutral"
            : online === 0
              ? "danger"
              : quiet > 0
                ? "warning"
                : "success"
        }
        secondary={
          live === 0
            ? t("overview.kpi.runnersNone")
            : quiet > 0
              ? t("overview.kpi.runnersQuiet", {
                  count: quiet,
                  queued: num(summary.data?.queued ?? 0),
                })
              : summary.data
                ? t("overview.kpi.queue", {
                    queued: num(summary.data.queued),
                    running: num(summary.data.running),
                  })
                : null
        }
      />
      <KpiTile
        testId="overview-kpi-storage"
        to="/admin/storage"
        icon={<HardDrive size={14} aria-hidden="true" />}
        label={t("overview.kpi.storage")}
        loading={storage.isPending && !storage.isError}
        error={failedEmpty(storage) ? failed : undefined}
        value={disk ? formatFileSize(usedBytes ?? disk.blob_bytes) : ""}
        progress={used}
        progressTone={storageTone}
        tone={storageTone === "neutral" ? "success" : storageTone}
        secondary={
          disk?.volume_total_bytes && disk.free_bytes !== null
            ? t("overview.kpi.storageFree", {
                free: formatFileSize(disk.free_bytes),
                total: formatFileSize(disk.volume_total_bytes),
              })
            : disk
              ? t("overview.kpi.storageProjects", { count: disk.projects })
              : null
        }
      />
      <KpiTile
        testId="overview-kpi-services"
        to="/admin/services"
        icon={<Activity size={14} aria-hidden="true" />}
        label={t("overview.kpi.services")}
        loading={services.isPending && !services.isError}
        error={failedEmpty(services) ? failed : undefined}
        value={num(okServices)}
        unit={t("overview.kpi.servicesOf", {
          total: num((services.data?.length ?? 0) - offServices),
        })}
        tone={
          downServices > 0
            ? "danger"
            : warnServices > 0
              ? "warning"
              : offServices > 0
                ? "neutral"
                : "success"
        }
        secondary={
          downServices > 0
            ? t("overview.kpi.servicesBad", { count: downServices })
            : warnServices > 0
              ? t("overview.kpi.servicesWarn", { count: warnServices })
              : offServices > 0
                ? t("overview.kpi.servicesOff", { count: offServices })
                : t("overview.kpi.servicesAllOk")
        }
      />
    </KpiGrid>
  );
};

const AttentionBlock = () => {
  const { t } = useTranslation("adminShell");
  const approvals = useApprovals(0);
  const runners = useRunnerSummary();
  const services = useServices();
  const storage = useStorage();
  const auth = useBootstrap().data?.auth;

  const items: Attention[] = [];
  const waiting = approvals.data?.total ?? 0;
  if (waiting > 0) {
    items.push({
      id: "approvals",
      tone: "warning",
      title: t("overview.attention.approvals", { count: waiting }),
      body: t("overview.attention.approvalsBody"),
      to: "/admin/users?tab=approvals",
    });
  }
  if (auth?.registration_mode === "open" && !auth.smtp_enabled) {
    items.push({
      id: "open-no-mail",
      tone: "danger",
      title: t("overview.attention.openNoMail"),
      body: t("overview.attention.openNoMailBody"),
      to: "/admin/settings",
    });
  } else if (auth && !auth.smtp_enabled) {
    items.push({
      id: "mail",
      tone: "info",
      title: t("overview.attention.mail"),
      body: t("overview.attention.mailBody"),
      to: "/admin/settings",
    });
  }
  // Счётчики раннеров от сервера; приостановленные молчат намеренно.
  const counts = runners.data;
  const online = counts?.online ?? 0;
  const quiet = counts ? quietRunners(counts) : 0;
  const working = online + quiet;
  if (counts && liveRunners(counts) === 0) {
    items.push({
      id: "runners-missing",
      tone: "warning",
      title: t("overview.attention.runnersMissing"),
      body: t("overview.attention.runnersMissingBody"),
      to: "/admin/runners?create=token",
    });
  } else if (working > 0 && online === 0) {
    items.push({
      id: "runners-none",
      tone: "danger",
      title: t("overview.attention.runnersNone"),
      body: t("overview.attention.runnersNoneBody"),
      to: "/admin/runners",
    });
  } else if (quiet > 0) {
    items.push({
      id: "runners-quiet",
      tone: "warning",
      title: t("overview.attention.runnersQuiet", { count: quiet }),
      body: t("overview.attention.runnersQuietBody"),
      to: "/admin/runners",
    });
  }
  // Раннеры уже разобраны выше по их собственному списку.
  const badServices = (services.data ?? []).filter(
    (s) => isBad(s) && s.kind !== "runners",
  );
  for (const s of badServices) {
    items.push({
      id: `service-${s.id}`,
      tone: s.status === "down" ? "danger" : "warning",
      title: t("overview.attention.service", {
        name: t(`overview.serviceKind.${s.kind}`),
        status: t(
          `overview.serviceStatus.${s.status === "down" ? "down" : "degraded"}`,
        ),
      }),
      // Причина от сервера бывает кодом (no_healthy_replica): такую не показываем.
      body:
        s.detail && !/^[a-z0-9_.-]+$/.test(s.detail)
          ? s.detail
          : t("overview.attention.serviceBody"),
      to: "/admin/services",
    });
  }
  if (storage.data && isLowSpace(storage.data)) {
    items.push({
      id: "low-space",
      tone: "danger",
      title: t("overview.attention.lowSpace"),
      body: t("overview.attention.lowSpaceBody", {
        free: formatFileSize(storage.data.free_bytes ?? 0),
      }),
      to: "/admin/storage",
    });
  }
  // Сначала то, что ломает работу сейчас.
  const order: Record<Tone, number> = { danger: 0, warning: 1, info: 2 };
  items.sort((a, b) => order[a.tone] - order[b.tone]);

  const queries = [approvals, runners, services, storage];
  const loading = queries.some((q) => q.isPending && !q.isError);
  const failed = queries.some((q) => q.isError);

  return (
    <Section
      title={t("overview.attention.title")}
      description={t("overview.attention.lead")}
      flush
      testId="overview-attention"
    >
      {items.length > 0 && (
        <SectionList label={t("overview.attention.title")}>
          {items.map((item) => (
            <ListRow
              key={item.id}
              testId={`overview-attention-${item.id}`}
              icon={TONE_ICON[item.tone]}
              tone={item.tone}
              title={item.title}
              description={item.body}
              to={item.to}
            />
          ))}
        </SectionList>
      )}
      {items.length === 0 && loading && (
        <TableSkeleton rows={2} columns={1} framed={false} />
      )}
      {items.length === 0 && !loading && !failed && (
        <div style={{ padding: "0 8px 8px" }}>
          <EmptyState
            compact
            icon={<CircleCheck size={15} style={{ color: "var(--c-ok)" }} />}
            title={t("overview.attention.allClear")}
            description={t("overview.attention.allClearBody")}
            testId="overview-attention-clear"
          />
        </div>
      )}
      {failed && (
        <div
          style={{
            padding: "4px 8px 8px",
            borderTop: items.length > 0 ? "1px solid var(--border)" : 0,
          }}
        >
          <ErrorState
            compact
            title={t("overview.attention.failed")}
            testId="overview-attention-failed"
            onRetry={() => {
              for (const q of queries) if (q.isError) void q.refetch();
            }}
          />
        </div>
      )}
    </Section>
  );
};

const ActivityBlock = () => {
  const { t } = useTranslation("adminShell");
  // Одна короткая страница журнала: имена людей и подписи целей сервер
  // отдаёт в строках, справочник людей не нужен.
  const audit = useRecentAudit(ACTIVITY_LIMIT);
  const label = useAuditActionLabel();
  const events: AdminAuditEvent[] = audit.data?.items ?? [];
  const now = useNow();

  return (
    <Section
      title={t("overview.activity.title")}
      actions={
        <Link
          to="/admin/audit"
          className="btn ghost sm"
          data-testid="overview-activity-all"
        >
          {t("overview.activity.all")}
        </Link>
      }
      flush
      testId="overview-activity"
    >
      {audit.isPending && (
        <TableSkeleton rows={4} columns={2} withAvatar framed={false} />
      )}
      {audit.isError && (
        <div style={{ padding: "4px 8px 8px" }}>
          <ErrorState
            compact
            title={t("overview.activity.failed")}
            testId="overview-activity-failed"
            onRetry={() => {
              void audit.refetch();
            }}
          />
        </div>
      )}
      {audit.isSuccess && events.length === 0 && (
        <EmptyState
          title={t("overview.activity.empty")}
          description={t("overview.activity.emptyBody")}
        />
      )}
      {events.length > 0 && (
        <SectionList label={t("overview.activity.title")}>
          {events.map((e) => {
            const actor = e.actor && !isPseudonym(e.actor) ? e.actor : null;
            const who = e.actor_id
              ? (actor?.name ?? t("overview.activity.unknown"))
              : t("overview.activity.system");
            const what = auditTarget(e)?.text ?? null;
            return (
              <ListRow
                key={e.id}
                testId={`overview-activity-${String(e.id)}`}
                leading={
                  e.actor_id ? (
                    <Avatar
                      name={actor?.name ?? null}
                      seed={e.actor_id}
                      size={26}
                    />
                  ) : (
                    // Действие самой установки: тот же значок, что в аудите.
                    <span
                      className="adm-avatar"
                      aria-hidden="true"
                      style={{ width: 26, height: 26 }}
                    >
                      <Cpu size={13} />
                    </span>
                  )
                }
                title={
                  <>
                    {label(e.action)}
                    {what && (
                      <span style={{ color: "var(--fg-2)" }}> · {what}</span>
                    )}
                  </>
                }
                description={who}
                meta={
                  <time
                    dateTime={e.at}
                    title={new Date(e.at).toLocaleString(localeTag())}
                  >
                    {formatPastTime(e.at, now)}
                  </time>
                }
              />
            );
          })}
        </SectionList>
      )}
    </Section>
  );
};

const QuickActions = () => {
  const { t } = useTranslation("adminShell");
  return (
    <Section title={t("overview.quick.title")} flush testId="overview-quick">
      <SectionList label={t("overview.quick.title")}>
        <ListRow
          testId="overview-quick-invite"
          icon={<UserPlus size={15} />}
          tone="accent"
          title={t("overview.quick.invite")}
          description={t("overview.quick.inviteHint")}
          to="/admin/users?tab=invitations"
        />
        <ListRow
          testId="overview-quick-token"
          icon={<KeyRound size={15} />}
          tone="accent"
          title={t("overview.quick.token")}
          description={t("overview.quick.tokenHint")}
          to="/admin/runners?create=token"
        />
        <ListRow
          testId="overview-quick-signin"
          icon={<SlidersHorizontal size={15} />}
          tone="accent"
          title={t("overview.quick.signIn")}
          description={t("overview.quick.signInHint")}
          to="/admin/settings"
        />
      </SectionList>
    </Section>
  );
};

const hostOf = (url: string): string => {
  try {
    return new URL(url).host;
  } catch {
    return url;
  }
};

// Почта на сводке берётся из проверки сервисов, как на странице «Сервисы»:
// настройки могут быть заполнены, а сервер почты не отвечать или не быть
// подключён в окружении.
const MAIL_DOT: Record<AdminService["status"], StatusDotStatus> = {
  ok: "success",
  degraded: "warning",
  down: "danger",
  unconfigured: "neutral",
};

const MailStatus = () => {
  const { t } = useTranslation("adminShell");
  const bootstrap = useBootstrap().data;
  const services = useServices();
  const smtp = services.data?.find((s) => s.kind === "smtp");
  if (smtp) {
    return (
      <span data-testid="overview-mail" data-status={smtp.status}>
        <StatusDot
          status={MAIL_DOT[smtp.status]}
          label={t(`overview.instance.mailStatus.${smtp.status}`)}
        />
      </span>
    );
  }
  // Проверка сервисов не ответила: показываем только, заполнены ли настройки.
  if (!bootstrap) return <>…</>;
  return (
    <span data-testid="overview-mail" data-status="settings">
      <StatusDot
        status={bootstrap.auth.smtp_enabled ? "neutral" : "warning"}
        label={
          bootstrap.auth.smtp_enabled
            ? t("overview.instance.mailFilled")
            : t("overview.instance.mailOff")
        }
      />
    </span>
  );
};

const InstanceBlock = () => {
  const { t } = useTranslation("adminShell");
  const bootstrap = useBootstrap().data;
  const instance = useInstanceSettings();
  return (
    <Section
      title={t("overview.instance.title")}
      actions={
        <Link to="/admin/instance" className="btn ghost sm">
          {t("overview.instance.edit")}
        </Link>
      }
      testId="overview-instance"
    >
      {instance.isError ? (
        <ErrorState
          compact
          onRetry={() => {
            void instance.refetch();
          }}
        />
      ) : (
        <dl className="adm-kv">
          <dt>{t("overview.instance.name")}</dt>
          <dd>{instance.data?.name ?? "…"}</dd>
          <dt>{t("overview.instance.address")}</dt>
          <dd title={instance.data?.public_url}>
            {instance.data ? hostOf(instance.data.public_url) : "…"}
          </dd>
          {bootstrap && (
            <>
              <dt>{t("overview.instance.registration")}</dt>
              <dd>
                {t(
                  `overview.instance.modes.${bootstrap.auth.registration_mode}`,
                )}
              </dd>
            </>
          )}
          <dt>{t("overview.instance.mail")}</dt>
          <dd>
            <MailStatus />
          </dd>
        </dl>
      )}
    </Section>
  );
};

/** Начальная страница админки: сводка установки. */
export const AdminOverview = () => {
  const { t } = useTranslation("adminShell");
  return (
    <AdminPage
      title={t("overview.title")}
      description={t("overview.lead")}
      pageTestId="admin-overview"
    >
      <Kpis />
      <div className="adm-overview-grid">
        <div className="adm-overview-col">
          <AttentionBlock />
          <ActivityBlock />
        </div>
        <div className="adm-overview-col">
          <QuickActions />
          <InstanceBlock />
        </div>
      </div>
    </AdminPage>
  );
};
