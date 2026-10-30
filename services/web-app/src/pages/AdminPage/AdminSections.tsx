import type { ReactNode } from "react";
import {
  Activity,
  CircleAlert,
  CircleCheck,
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
} from "@shared/ui";
import {
  useBootstrap,
  type AdminAuditEvent,
  type AdminService,
  type AdminUser,
} from "@entities/session";
import { useInstanceSettings } from "@features/admin-install";
import {
  isLowSpace,
  runnerStatus,
  useNow,
  useQueueSummary,
  useRunners,
  useServices,
  useStorage,
} from "@features/admin-ops";
import {
  useApprovals,
  useAudit,
  useAuditActionLabel,
  useUsers,
} from "@features/admin-users";

// Сводка установки: числа, то, что ждёт решения, последние действия и быстрые
// переходы. Каждый блок живёт своим запросом: упавший показывает ошибку у
// себя, остальная страница работает.

const ACTIVITY_LIMIT = 7;

// Поля details, которые сами по себе читаются как название цели.
const DETAIL_NAMES = ["name", "label", "email", "slug"] as const;

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

// Служебные идентификаторы (u_01hx…, uuid) людям ни о чём не говорят.
const looksLikeId = (value: string): boolean =>
  /^[a-z]{1,6}_[0-9a-z]{6,}$/i.test(value) ||
  /^[0-9a-f]{8}-[0-9a-f]{4}-/i.test(value);

const isBad = (s: AdminService): boolean =>
  s.status === "degraded" || s.status === "down";

/** Число по правилам языка интерфейса. */
const useNumber = (): ((value: number) => string) => {
  const fmt = new Intl.NumberFormat(localeTag());
  return (value) => fmt.format(value);
};

const Kpis = () => {
  const { t } = useTranslation("adminShell");
  const num = useNumber();
  const users = useUsers(ALL_USERS);
  const approvals = useApprovals(0);
  const runners = useRunners();
  const summary = useQueueSummary();
  const services = useServices();
  const storage = useStorage();
  const now = useNow();

  const waiting = approvals.data?.total ?? 0;
  const live = (runners.data ?? []).filter((r) => !r.revoked);
  const online = live.filter((r) => runnerStatus(r, now) === "online").length;
  const okServices = (services.data ?? []).filter(
    (s) => s.status === "ok",
  ).length;
  // Неподключённый сервис не сломан: его не считаем ни в норме, ни в сбое.
  const offServices = (services.data ?? []).filter(
    (s) => s.status === "unconfigured",
  ).length;
  const badServices = (services.data ?? []).filter(isBad).length;
  const disk = storage.data;
  const used =
    disk?.volume_total_bytes && disk.free_bytes !== null
      ? ((disk.volume_total_bytes - disk.free_bytes) /
          disk.volume_total_bytes) *
        100
      : null;
  const low = disk ? isLowSpace(disk) : false;
  const failed = t("overview.kpi.failed");

  return (
    <KpiGrid>
      <KpiTile
        testId="overview-kpi-people"
        to="/admin/users"
        icon={<Users size={14} aria-hidden="true" />}
        label={t("overview.kpi.people")}
        loading={users.isPending && !users.isError}
        error={users.isError ? failed : undefined}
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
        error={runners.isError ? failed : undefined}
        value={num(online)}
        unit={
          live.length > 0
            ? t("overview.kpi.runnersOf", { total: num(live.length) })
            : undefined
        }
        tone={live.length > 0 && online === 0 ? "danger" : "neutral"}
        secondary={
          live.length === 0
            ? t("overview.kpi.runnersNone")
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
        error={storage.isError ? failed : undefined}
        value={disk ? formatFileSize(disk.blob_bytes) : ""}
        progress={used}
        progressTone={low ? "warning" : "neutral"}
        tone={low ? "warning" : "neutral"}
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
        error={services.isError ? failed : undefined}
        value={num(okServices)}
        unit={t("overview.kpi.servicesOf", {
          total: num((services.data?.length ?? 0) - offServices),
        })}
        tone={
          badServices > 0 ? "danger" : offServices > 0 ? "neutral" : "success"
        }
        secondary={
          badServices > 0
            ? t("overview.kpi.servicesBad", { count: badServices })
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
  const runners = useRunners();
  const services = useServices();
  const storage = useStorage();
  const auth = useBootstrap().data?.auth;
  const now = useNow();

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
  const live = (runners.data ?? []).filter((r) => !r.revoked && !r.paused);
  const statuses = live.map((r) => runnerStatus(r, now));
  const online = statuses.filter((s) => s === "online").length;
  const quiet = statuses.filter((s) => s === "stale" || s === "offline").length;
  if (runners.data?.every((r) => r.revoked)) {
    items.push({
      id: "runners-missing",
      tone: "warning",
      title: t("overview.attention.runnersMissing"),
      body: t("overview.attention.runnersMissingBody"),
      to: "/admin/runners?create=token",
    });
  } else if (live.length > 0 && online === 0) {
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
      tone: "warning",
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
  const audit = useAudit("");
  const users = useUsers(ALL_USERS);
  const approvals = useApprovals(0);
  const label = useAuditActionLabel();

  const people = new Map<string, AdminUser>();
  for (const u of [
    ...(users.data?.items ?? []),
    ...(approvals.data?.items ?? []),
  ]) {
    people.set(u.id, u);
  }
  const events: AdminAuditEvent[] = (audit.data?.pages[0]?.items ?? []).slice(
    0,
    ACTIVITY_LIMIT,
  );
  const now = useNow();

  // На что направлено действие: человек по id, иначе понятное поле из details.
  const target = (e: AdminAuditEvent): string | null => {
    const person = e.target ? people.get(e.target) : undefined;
    if (person) return person.name;
    for (const key of DETAIL_NAMES) {
      const value = e.details[key];
      if (typeof value === "string" && value !== "") return value;
    }
    return e.target && !looksLikeId(e.target) ? e.target : null;
  };

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
            const actor = e.actor_id ? people.get(e.actor_id) : undefined;
            const who = e.actor_id
              ? (actor?.name ?? t("overview.activity.unknown"))
              : t("overview.activity.system");
            const what = target(e);
            return (
              <ListRow
                key={e.id}
                testId={`overview-activity-${String(e.id)}`}
                leading={
                  <Avatar
                    name={actor?.name ?? null}
                    seed={e.actor_id}
                    size={26}
                  />
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
              <dt>{t("overview.instance.version")}</dt>
              <dd className="mono" style={{ fontSize: 12 }}>
                {bootstrap.version}
              </dd>
              <dt>{t("overview.instance.registration")}</dt>
              <dd>
                {t(
                  `overview.instance.modes.${bootstrap.auth.registration_mode}`,
                )}
              </dd>
              <dt>{t("overview.instance.mail")}</dt>
              <dd>
                <StatusDot
                  status={bootstrap.auth.smtp_enabled ? "success" : "warning"}
                  label={
                    bootstrap.auth.smtp_enabled
                      ? t("overview.instance.mailOn")
                      : t("overview.instance.mailOff")
                  }
                />
              </dd>
            </>
          )}
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
