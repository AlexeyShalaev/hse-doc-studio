import { useState, type ReactNode } from "react";
import {
  Activity,
  Cpu,
  Building2,
  ChevronRight,
  FolderOpen,
  ListFilter,
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
import {
  formatPastTime,
  localeTag,
  toast,
  useCursorList,
  useListQueryState,
} from "@shared/lib";
import {
  Button,
  DateRangeFilter,
  EmptyState,
  ErrorState,
  FilterBar,
  FilterMenu,
  NoResults,
  PageHeader,
  Pagination,
  PersonCell,
  PickerFilter,
  Spinner,
  TableSkeleton,
  useDateRangeLabel,
  usePickedItem,
  type ActiveFilter,
} from "@shared/ui";
import { adminPickers, type AdminAuditEvent } from "@entities/session";
import { AUDIT_CATEGORIES, auditApi } from "../api/auditApi";
import { auditKeys } from "../api/auditQueries";
import {
  auditCategory,
  auditTarget,
  auditTone,
  daysAgo,
  groupByDay,
  isPseudonym,
  looksLikeId,
  type AuditCategory,
} from "../lib/auditFormat";
import { useAuditActionLabel } from "../lib/auditLabel";
import { detailText } from "../lib/format";

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

// Состояние журнала в адресе: поиск, разделы, человек, объект и период.
// Сортировки нет: журнал всегда идёт от новых к старым.
const LIST = {
  mode: "cursor",
  filters: {
    category: { multi: true, values: AUDIT_CATEGORIES },
    actor_id: {},
    target: {},
    from: { date: "from" },
    to: { date: "to" },
  },
} as const;

// Пикер людей ищет на сервере среди всех людей установки.
const PEOPLE = adminPickers.users();

const idOf = (e: AdminAuditEvent): string => String(e.id);

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
        else if (
          typeof raw === "number" &&
          known(`audit.detailUnits.${key}_other`)
        )
          // Число с единицей по правилам языка: «7 дней», а не «дней: 7».
          value = t(`audit.detailUnits.${key}`, { count: raw });
        else if (typeof raw === "number")
          value = raw.toLocaleString(localeTag());
        else if (typeof raw === "string" && known(`audit.values.${raw}`))
          value = t(`audit.values.${raw}`);
        else if (typeof raw === "string") machine = looksLikeId(raw);
        return { key, label, value, machine };
      })
      .filter((d) => d.value !== "");
};

/**
 * Раздел «Аудит»: журнал по дням, новые сверху. Поиск, разделы, человек и
 * период считает сервер; дальше журнал подгружается по курсору.
 */
export const AuditLog = () => {
  const { t } = useTranslation("adminUsers");
  const state = useListQueryState(LIST);
  const log = useCursorList({
    state,
    queryKey: auditKeys.all,
    fetchPage: auditApi.page,
    getId: idOf,
  });
  const [open, setOpen] = useState<ReadonlySet<number>>(new Set());
  const label = useAuditActionLabel();
  const detailsOf = useDetails();

  const actorId = state.filter("actor_id") || null;
  const targetId = state.filter("target") || null;
  const period = {
    from: state.filter("from") || null,
    to: state.filter("to") || null,
  };
  const periodLabel = useDateRangeLabel(period);
  const picked = usePickedItem(PEOPLE, actorId, null);
  const events = log.items;

  /** Имя человека; псевдоним удалённого и неизвестный id людям не показываем. */
  const actorName = (e: AdminAuditEvent): string => {
    if (!e.actor_id) return t("audit.system");
    const actor = e.actor ?? null;
    return actor && !isPseudonym(actor) ? actor.name : t("audit.unknownActor");
  };

  // Подписи выбранных условий. Строки журнала уже отобраны сервером, так что
  // имя человека или объекта берётся из любой из них.
  const first = events[0];
  const shownActor =
    picked?.name ??
    (first && actorId && first.actor_id === actorId ? actorName(first) : null);
  const shownTarget =
    first && targetId && first.target === targetId
      ? (auditTarget(first)?.text ?? targetId)
      : targetId;

  const active: ActiveFilter[] = [
    ...(state.q
      ? [
          {
            id: "q",
            label: t("audit.filters.search"),
            value: state.q,
            onRemove: () => {
              state.setQ("");
            },
          },
        ]
      : []),
    ...(state.filters.category.length > 0
      ? [
          {
            id: "category",
            label: t("audit.group"),
            value: state.filters.category
              .map((c) => t(`audit.groups.${c}`))
              .join(", "),
            onRemove: () => {
              state.setFilter("category", null);
            },
          },
        ]
      : []),
    ...(actorId
      ? [
          {
            id: "actor",
            label: t("audit.filters.actor"),
            value: shownActor ?? t("audit.unknownActor"),
            onRemove: () => {
              state.setFilter("actor_id", null);
            },
          },
        ]
      : []),
    ...(targetId
      ? [
          {
            id: "target",
            label: t("audit.filters.target"),
            value: shownTarget ?? targetId,
            onRemove: () => {
              state.setFilter("target", null);
            },
          },
        ]
      : []),
    ...(periodLabel
      ? [
          {
            id: "period",
            label: t("audit.filters.period"),
            value: periodLabel,
            onRemove: () => {
              state.setFilters({ from: null, to: null });
            },
          },
        ]
      : []),
  ];

  const days = groupByDay(events);
  const now = new Date();
  const lastDay = days[days.length - 1]?.key;

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

  const row = (e: AdminAuditEvent, today: boolean) => {
    const target = auditTarget(e);
    const details = detailsOf(e.details, target?.key ?? null);
    const actor = e.actor && !isPseudonym(e.actor) ? e.actor : null;
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
    const byActor = e.actor_id !== null && e.actor_id !== actorId;
    const byTarget = e.target !== null && e.target !== targetId;
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
                  {target.text}
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
              <dd>
                {actor?.email ? `${actor.name} (${actor.email})` : actorName(e)}
              </dd>
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
            {(byActor || byTarget) && (
              <div className="adm-audit-jump">
                {byActor && (
                  <Button
                    variant="ghost"
                    size="sm"
                    type="button"
                    data-testid={`audit-by-actor-${String(e.id)}`}
                    onClick={() => {
                      state.setFilter("actor_id", e.actor_id);
                    }}
                  >
                    <ListFilter size={13} aria-hidden="true" />
                    {t("audit.show.byActor")}
                  </Button>
                )}
                {byTarget && (
                  <Button
                    variant="ghost"
                    size="sm"
                    type="button"
                    data-testid={`audit-by-target-${String(e.id)}`}
                    onClick={() => {
                      state.setFilter("target", e.target);
                    }}
                  >
                    <ListFilter size={13} aria-hidden="true" />
                    {t("audit.show.byTarget")}
                  </Button>
                )}
              </div>
            )}
          </div>
        )}
      </li>
    );
  };

  // Пока идёт запрос с новыми условиями, на экране прежние строки, приглушённые.
  const stale = log.query.isPlaceholderData;
  const refreshing = log.isFetching && !log.isLoadingMore;
  const failedFirst = log.isError && events.length === 0;
  const failedMore = log.query.isFetchNextPageError;

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
            disabled={log.isFetching}
            onClick={() => {
              log.refresh().catch(() => {
                toast.error(t("audit.loadFailed"));
              });
            }}
            data-testid="audit-refresh"
          >
            {refreshing ? (
              <Spinner size="sm" />
            ) : (
              <RefreshCw size={13} aria-hidden="true" />
            )}
            {t("audit.refresh")}
          </Button>
        }
      />
      <FilterBar
        search={state.q}
        onSearchChange={state.setQ}
        searchLabel={t("audit.search")}
        searchPlaceholder={t("audit.searchPlaceholder")}
        busy={refreshing}
        onReset={state.reset}
        active={active}
        extra={
          <>
            <FilterMenu
              label={t("audit.group")}
              testId="audit-filter-category"
              values={state.filters.category}
              onChange={(values) => {
                state.setFilter("category", values);
              }}
              options={AUDIT_CATEGORIES.map((c) => ({
                value: c,
                label: t(`audit.groups.${c}`),
              }))}
            />
            <PickerFilter
              label={t("audit.filters.actor")}
              testId="audit-filter-actor"
              source={PEOPLE}
              value={actorId}
              searchPlaceholder={t("audit.filters.actorSearch")}
              onChange={(item) => {
                state.setFilter("actor_id", item?.id ?? null);
              }}
            />
            <DateRangeFilter
              testId="audit-filter-period"
              value={period}
              onChange={({ from, to }) => {
                state.setFilters({ from, to });
              }}
            />
          </>
        }
      />
      {failedFirst && (
        <ErrorState
          framed
          title={t("audit.loadFailed")}
          description={t("audit.loadFailedBody")}
          retrying={log.isFetching}
          onRetry={() => {
            void log.refetch();
          }}
          testId="audit-failed"
        />
      )}
      {log.isLoading && (
        <TableSkeleton rows={6} columns={3} withAvatar testId="audit-loading" />
      )}
      {!log.isLoading &&
        !log.isError &&
        events.length === 0 &&
        (state.isFiltered ? (
          <NoResults
            framed
            query={state.searchOnly}
            onReset={state.reset}
            testId="audit-empty"
          />
        ) : (
          <EmptyState
            framed
            icon={<ScrollText size={18} />}
            title={t("audit.empty.title")}
            description={t("audit.empty.body")}
            testId="audit-empty"
          />
        ))}
      {days.length > 0 && (
        <div
          className="adm-audit"
          aria-busy={stale}
          style={{ opacity: stale ? 0.6 : 1, transition: "opacity 0.12s" }}
        >
          {days.map((day) => (
            <section
              key={day.key}
              className="adm-audit-day"
              aria-label={dayLabel(day.key)}
            >
              <div className="adm-audit-dayhead">
                <span>{dayLabel(day.key)}</span>
                {/* Последний день может продолжаться на следующей странице:
                    его неполное число не показываем. */}
                {(day.key !== lastDay || !log.hasMore) && (
                  <span>
                    {t("audit.dayCount", { count: day.events.length })}
                  </span>
                )}
              </div>
              <ul className="adm-audit-list" aria-label={t("audit.caption")}>
                {day.events.map((e) => row(e, daysAgo(day.key, now) === 0))}
              </ul>
            </section>
          ))}
          {failedMore && (
            <div style={{ padding: "4px 12px 8px" }}>
              <ErrorState
                compact
                title={t("audit.loadFailed")}
                retrying={log.isLoadingMore}
                onRetry={log.loadMore}
                testId="audit-more-failed"
              />
            </div>
          )}
          <div className="adm-audit-foot" style={{ display: "block" }}>
            <Pagination
              {...log.pagination}
              pageSize={state.pageSize}
              pageSizes={state.pageSizes}
              onPageSizeChange={state.setPageSize}
            />
          </div>
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
