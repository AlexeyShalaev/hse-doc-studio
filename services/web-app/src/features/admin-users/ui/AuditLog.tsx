import { useMemo, useState, type ReactNode } from "react";
import {
  Activity,
  Cpu,
  Building2,
  ChevronRight,
  FolderOpen,
  LogIn,
  Mail,
  RefreshCw,
  ScrollText,
  Server,
  Settings2,
  UserCog,
  Users,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { formatPastTime, localeTag } from "@shared/lib";
import {
  Button,
  EmptyState,
  ErrorState,
  FilterBar,
  PageHeader,
  PersonCell,
  Spinner,
  TableSkeleton,
} from "@shared/ui";
import type { AdminAuditEvent, AdminUser } from "@entities/session";
import { useApprovals, useAudit, useUsers } from "../api/adminUsersQueries";
import {
  auditCategory,
  auditTarget,
  auditTone,
  daysAgo,
  groupByDay,
  looksLikeId,
  type AuditCategory,
} from "../lib/auditFormat";
import { useAuditActionLabel } from "../lib/auditLabel";
import { detailText } from "../lib/format";

const GROUPS = [
  "auth.",
  "admin.",
  "invite.",
  "org.",
  "group.",
  "settings.",
  "runner.",
  "project.",
] as const;

const ALL_USERS = { q: "", status: "", page: 0 } as const;

const ICON: Record<AuditCategory, ReactNode> = {
  auth: <LogIn size={14} />,
  admin: <UserCog size={14} />,
  invite: <Mail size={14} />,
  org: <Building2 size={14} />,
  group: <Users size={14} />,
  settings: <Settings2 size={14} />,
  runner: <Server size={14} />,
  project: <FolderOpen size={14} />,
  other: <Activity size={14} />,
};

const SUMMARY_LIMIT = 2;

const fullDate = (iso: string): string => {
  const date = new Date(iso);
  return Number.isNaN(date.getTime())
    ? iso
    : date.toLocaleString(localeTag(), {
        dateStyle: "long",
        timeStyle: "medium",
      });
};

type Detail = { key: string; label: string; value: string; machine: boolean };

/** Подписи и значения details на языке интерфейса; неизвестный ключ читается как есть. */
const useDetails = (): ((
  details: Record<string, unknown>,
  skip: string | null,
) => Detail[]) => {
  const { t, i18n } = useTranslation("adminUsers");
  const known = (key: string) => i18n.exists(key, { ns: "adminUsers" });
  return (details, skip) =>
    Object.entries(details)
      .filter(([key]) => key !== skip)
      .map(([key, raw]) => {
        const labelKey = `audit.detailKeys.${key}`;
        const label = known(labelKey)
          ? t(labelKey)
          : key.charAt(0).toUpperCase() + key.slice(1).replaceAll("_", " ");
        let value = detailText(raw);
        let machine = typeof raw === "object" && raw !== null;
        if (typeof raw === "boolean") value = t(raw ? "audit.yes" : "audit.no");
        else if (typeof raw === "number")
          value = raw.toLocaleString(localeTag());
        else if (typeof raw === "string" && known(`audit.values.${raw}`))
          value = t(`audit.values.${raw}`);
        else if (typeof raw === "string") machine = looksLikeId(raw);
        return { key, label, value, machine };
      })
      .filter((d) => d.value !== "");
};

/** Раздел «Аудит»: журнал по дням, новые сверху, дальше подгружается по кнопке. */
export const AuditLog = () => {
  const { t } = useTranslation("adminUsers");
  const [group, setGroup] = useState("");
  const audit = useAudit(group);
  const users = useUsers(ALL_USERS);
  const approvals = useApprovals(0);
  const [search, setSearch] = useState("");
  const [open, setOpen] = useState<ReadonlySet<number>>(new Set());
  const label = useAuditActionLabel();
  const detailsOf = useDetails();

  const people = useMemo(() => {
    const map = new Map<string, AdminUser>();
    for (const u of [
      ...(users.data?.items ?? []),
      ...(approvals.data?.items ?? []),
    ]) {
      map.set(u.id, u);
    }
    return map;
  }, [users.data, approvals.data]);

  const all = useMemo<AdminAuditEvent[]>(
    () => audit.data?.pages.flatMap((p) => p.items) ?? [],
    [audit.data],
  );
  const filtering = group !== "" || search.trim() !== "";

  const actorName = (e: AdminAuditEvent): string =>
    e.actor_id
      ? (people.get(e.actor_id)?.name ?? t("audit.unknownActor"))
      : t("audit.system");
  const targetText = (e: AdminAuditEvent): string | null => {
    const target = auditTarget(e, people);
    if (!target) return null;
    return target.kind === "person" ? target.user.name : target.text;
  };

  // Поиск идёт по уже загруженным записям: подпись, кто, на что и подробности.
  const needle = search.trim().toLowerCase();
  const events =
    needle === ""
      ? all
      : all.filter((e) =>
          [
            label(e.action),
            e.action,
            actorName(e),
            people.get(e.actor_id ?? "")?.email ?? "",
            targetText(e) ?? "",
            ...Object.values(e.details).map(detailText),
          ].some((part) => part.toLowerCase().includes(needle)),
        );
  const days = groupByDay(events);
  const now = new Date();

  const dayLabel = (key: string): string => {
    const ago = daysAgo(key, now);
    if (ago === 0) return t("audit.today");
    if (ago === 1) return t("audit.yesterday");
    const [y, m, d] = key.split("-").map(Number);
    const date = new Date(y ?? 1970, (m ?? 1) - 1, d ?? 1);
    return date.toLocaleDateString(localeTag(), {
      day: "numeric",
      month: "long",
      weekday: "short",
      ...(date.getFullYear() === now.getFullYear() ? {} : { year: "numeric" }),
    });
  };

  const timeOf = (iso: string, today: boolean): string => {
    if (today) return formatPastTime(iso, now);
    const date = new Date(iso);
    return Number.isNaN(date.getTime())
      ? iso
      : date.toLocaleTimeString(localeTag(), {
          hour: "2-digit",
          minute: "2-digit",
        });
  };

  const toggle = (id: number) => {
    setOpen((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const resetFilters = () => {
    setGroup("");
    setSearch("");
  };

  const row = (e: AdminAuditEvent, today: boolean) => {
    const target = auditTarget(e, people);
    const details = detailsOf(
      e.details,
      target?.kind === "text" ? target.key : null,
    );
    const actor = e.actor_id ? people.get(e.actor_id) : undefined;
    const expanded = open.has(e.id);
    const panelId = `audit-panel-${String(e.id)}`;
    const summary = details
      .slice(0, SUMMARY_LIMIT)
      .map((d) => `${d.label}: ${d.value}`)
      .join(" · ");
    const who = e.actor_id ? (
      <PersonCell
        size="sm"
        id={e.actor_id}
        name={actor?.name ?? null}
        email={actor?.email ?? null}
        fallback={t("audit.unknownActor")}
      />
    ) : (
      <span className="adm-person">
        <span
          className="adm-avatar"
          aria-hidden="true"
          style={{ width: 20, height: 20 }}
        >
          <Cpu size={11} />
        </span>
        <span className="adm-person-text">
          <span className="adm-person-name">{t("audit.system")}</span>
        </span>
      </span>
    );
    return (
      <li key={e.id} data-testid={`audit-${String(e.id)}`}>
        <button
          type="button"
          className="adm-audit-row"
          aria-expanded={expanded}
          aria-controls={panelId}
          onClick={() => {
            toggle(e.id);
          }}
        >
          <span
            className="adm-audit-icon"
            data-tone={auditTone(e.action)}
            aria-hidden="true"
          >
            {ICON[auditCategory(e.action)]}
          </span>
          <span className="adm-audit-what">
            <span className="adm-audit-title">
              <span>{label(e.action)}</span>
              {target && (
                <span className="adm-audit-target">
                  {" · "}
                  {target.kind === "person" ? target.user.name : target.text}
                </span>
              )}
            </span>
            {summary && <span className="adm-audit-sub">{summary}</span>}
            <span className="adm-audit-sub" data-mobile="true">
              {actorName(e)}
            </span>
          </span>
          {who}
          <time
            className="adm-audit-time"
            dateTime={e.at}
            title={fullDate(e.at)}
          >
            {timeOf(e.at, today)}
          </time>
          <ChevronRight
            size={14}
            className="adm-audit-chevron"
            aria-hidden="true"
          />
        </button>
        {expanded && (
          <div
            id={panelId}
            className="adm-audit-details"
            data-testid={`audit-details-${String(e.id)}`}
          >
            <dl className="adm-kv">
              <dt>{t("audit.detail.when")}</dt>
              <dd>{fullDate(e.at)}</dd>
              <dt>{t("audit.detail.actor")}</dt>
              <dd>{actor ? `${actor.name} (${actor.email})` : actorName(e)}</dd>
              {details.map((d) => (
                <FragmentKV key={d.key} label={d.label} machine={d.machine}>
                  {d.value}
                </FragmentKV>
              ))}
              <dt>{t("audit.detail.code")}</dt>
              <dd className="mono" style={{ fontSize: 11.5 }}>
                {e.action}
              </dd>
              {e.target && (
                <>
                  <dt>{t("audit.detail.target")}</dt>
                  <dd className="mono" style={{ fontSize: 11.5 }}>
                    {e.target}
                  </dd>
                </>
              )}
            </dl>
          </div>
        )}
      </li>
    );
  };

  return (
    <div
      className="flex flex-col"
      style={{ gap: 16, flex: 1 }}
      data-testid="audit-log"
    >
      <PageHeader
        title={t("audit.title")}
        description={t("audit.lead")}
        actions={
          <Button
            variant="ghost"
            size="sm"
            type="button"
            disabled={audit.isFetching}
            onClick={() => {
              void audit.refetch();
            }}
            data-testid="audit-refresh"
          >
            {audit.isFetching && !audit.isFetchingNextPage ? (
              <Spinner size="sm" />
            ) : (
              <RefreshCw size={13} aria-hidden="true" />
            )}
            {t("audit.refresh")}
          </Button>
        }
      />
      <FilterBar
        search={search}
        onSearchChange={setSearch}
        searchLabel={t("audit.search")}
        searchPlaceholder={t("audit.search")}
        filters={[
          {
            id: "group",
            label: t("audit.group"),
            value: group,
            onChange: setGroup,
            options: GROUPS.map((g) => ({
              value: g,
              label: t(`audit.groups.${g.slice(0, -1)}`),
            })),
          },
        ]}
        onReset={resetFilters}
      />
      {audit.isError && (
        <ErrorState
          framed
          title={t("audit.loadFailed")}
          description={t("audit.loadFailedBody")}
          retrying={audit.isFetching}
          onRetry={() => {
            void audit.refetch();
          }}
          testId="audit-failed"
        />
      )}
      {audit.isPending && (
        <TableSkeleton rows={6} columns={3} withAvatar testId="audit-loading" />
      )}
      {audit.isSuccess && events.length === 0 && (
        <EmptyState
          framed
          icon={<ScrollText size={18} />}
          title={t(filtering ? "audit.noMatch.title" : "audit.empty.title")}
          description={t(filtering ? "audit.noMatch.body" : "audit.empty.body")}
          testId="audit-empty"
          action={
            filtering ? (
              <Button
                variant="secondary"
                size="sm"
                type="button"
                onClick={resetFilters}
              >
                {t("audit.resetFilters")}
              </Button>
            ) : undefined
          }
        />
      )}
      {days.length > 0 && (
        <div className="adm-audit">
          {days.map((day) => (
            <section
              key={day.key}
              className="adm-audit-day"
              aria-label={dayLabel(day.key)}
            >
              <div className="adm-audit-dayhead">
                <span>{dayLabel(day.key)}</span>
                <span>{t("audit.dayCount", { count: day.events.length })}</span>
              </div>
              <ul className="adm-audit-list" aria-label={t("audit.caption")}>
                {day.events.map((e) => row(e, daysAgo(day.key, now) === 0))}
              </ul>
            </section>
          ))}
          {audit.hasNextPage && (
            <div className="adm-audit-foot">
              <Button
                variant="ghost"
                size="sm"
                type="button"
                disabled={audit.isFetchingNextPage}
                data-testid="audit-more"
                onClick={() => {
                  void audit.fetchNextPage();
                }}
              >
                {audit.isFetchingNextPage && <Spinner size="sm" />}
                {t("audit.more")}
              </Button>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

const FragmentKV = ({
  label,
  machine,
  children,
}: {
  label: string;
  machine: boolean;
  children: string;
}) => (
  <>
    <dt>{label}</dt>
    <dd
      className={machine ? "mono" : undefined}
      style={machine ? { fontSize: 11.5 } : undefined}
    >
      {children}
    </dd>
  </>
);
