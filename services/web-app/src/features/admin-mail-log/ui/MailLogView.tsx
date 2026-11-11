import { useCallback, useMemo } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { Cpu, FolderOpen, Globe, Mail, RefreshCw, User } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import {
  localeTag,
  type CursorPaginationState,
  type PickerItem,
} from "@shared/lib";
import {
  Badge,
  Button,
  DataTable,
  DateRangeFilter,
  ErrorState,
  FilterBar,
  FilterMenu,
  Notice,
  PageHeader,
  PersonCell,
  PickerFilter,
  Spinner,
  isoDay,
  useDateRangeLabel,
  usePickedItem,
  type ActiveFilter,
  type FilterOption,
} from "@shared/ui";
import { adminPickers } from "@entities/session";
import type {
  MailLogFilterName,
  MailLogListState,
} from "../api/mailLogQueries";
import {
  MAIL_FAILURES,
  MAIL_SKIP_REASONS,
  MAIL_STATUSES,
  MAIL_TEMPLATE_GROUPS,
  isKnownMailTemplate,
  type MailLogEntry,
  type MailLogSummary,
  type MailStatus,
  type MailTemplateGroup,
} from "../api/schemas";
import { mailFailureOf, mailHintOf, skippedCount } from "../lib/mailLog";
import { mailWhen } from "../lib/when";
import "./mailLog.css";

/** Блок «Почта (SMTP)» в «Вход и регистрация»: туда ведут плашка и подсказка. */
export const SMTP_SETTINGS_PATH = "/admin/settings#admin-smtp";
/** «Хранение данных»: там меняют срок журнала писем. */
const RETENTION_PATH = "/admin/data";

// Ширины колонок: пустая выдача не перекладывает шапку.
const COLUMN_WIDTHS = {
  at: 136,
  to: 240,
  status: 200,
  cause: 200,
};

const STATUS_BADGE: Record<
  MailStatus,
  "success" | "error" | "default" | "subtle"
> = {
  sent: "success",
  failed: "error",
  not_sent: "default",
  suppressed: "default",
};

// Пикеры ищут на сервере среди всех людей и проектов установки.
const PEOPLE = adminPickers.users();
const PROJECTS = adminPickers.projects();

const GROUPS = Object.keys(MAIL_TEMPLATE_GROUPS) as MailTemplateGroup[];

export type MailLogViewProps = {
  /** Поиск и фильтры в адресе страницы (MAIL_LOG_LIST). */
  state: MailLogListState;
  /** Загруженные страницы подряд, новые первыми. */
  rows: readonly MailLogEntry[];
  /** Идёт запрос: первая загрузка (скелет) или новые условия (строки приглушены). */
  loading: boolean;
  /** Первая страница не загрузилась: строк нет. */
  failed: boolean;
  /** Следующая страница не загрузилась: строки остаются, под ними повтор. */
  failedMore?: boolean | undefined;
  /** «Показать ещё» по курсору сервера. */
  pagination: CursorPaginationState;
  /** Итоги за сутки; null, пока не пришли или не загрузились. */
  summary: MailLogSummary | null;
  /** Сейчас, мс: «сегодня», «вчера» и фильтр «за сутки». */
  now: number;
  /** Открытая карточка (`?mail=<id>`). */
  selectedId: number | null;
  /** Идёт «Обновить». */
  refreshing?: boolean | undefined;
  onOpen: (row: MailLogEntry) => void;
  onRefresh: () => void;
  onRetry: () => void;
  onRetryMore?: (() => void) | undefined;
};

/** Подпись вида письма из подписей образцов в «Вход и регистрация». */
const useTemplateLabel = () => {
  const { t } = useTranslation("adminMail");
  const { t: ts } = useTranslation("adminSettings");
  return useCallback(
    (template: string): string =>
      isKnownMailTemplate(template)
        ? ts(`mailPreview.names.${template}`)
        : t("templateGone", { template }),
    [t, ts],
  );
};

/**
 * Причина словами: пропуск («почта не настроена») или класс сбоя («SMTP-сервер отклонил логин
 * или пароль»); незнакомое значение как есть.
 */
const useReasonText = () => {
  const { t } = useTranslation("adminMail");
  return useCallback(
    (reason: string): string =>
      (MAIL_SKIP_REASONS as readonly string[]).includes(reason)
        ? t(`reason.${reason}`)
        : (MAIL_FAILURES as readonly string[]).includes(reason)
          ? t(`failure.${reason}`)
          : reason,
    [t],
  );
};

/** Второе слово итога: причина пропуска или класс сбоя (неизвестный класс как `other`). */
const useOutcomeReason = () => {
  const { t } = useTranslation("adminMail");
  const reasonText = useReasonText();
  return useCallback(
    (row: Pick<MailLogEntry, "status" | "reason">): string | null => {
      if (row.status === "failed") {
        return t(`failure.${mailFailureOf(row.reason)}`);
      }
      if (row.reason === null || row.status === "sent") return null;
      return reasonText(row.reason);
    },
    [t, reasonText],
  );
};

/**
 * Журнал писем (docs/design/mail-log.md, 4.1): шапка, плашка «Почта не настроена», полоса за
 * сутки с подсказкой, фильтры в адресе и таблица по курсору. Строка открывает карточку письма.
 */
export const MailLogView = ({
  state,
  rows,
  loading,
  failed,
  failedMore = false,
  pagination,
  summary,
  now,
  selectedId,
  refreshing = false,
  onOpen,
  onRefresh,
  onRetry,
  onRetryMore,
}: MailLogViewProps) => {
  const { t, i18n } = useTranslation("adminMail");
  const templateLabel = useTemplateLabel();
  const outcomeReason = useOutcomeReason();
  const reasonText = useReasonText();
  const locale = localeTag();

  const recipientId = state.filter("recipient_id") || null;
  const projectId = state.filter("project_id") || null;
  const period = {
    from: state.filter("from") || null,
    to: state.filter("to") || null,
  };
  const periodLabel = useDateRangeLabel(period);
  const pickedPerson = usePickedItem(PEOPLE, recipientId, null);
  const pickedProject = usePickedItem(PROJECTS, projectId, null);

  // Имя выбранного по строкам на экране: при фильтре по человеку или проекту каждая строка о нём.
  const shownPerson =
    pickedPerson?.name ??
    rows.find((r) => r.to_user?.id === recipientId)?.to_user?.name ??
    recipientId;
  const shownProject =
    pickedProject?.name ??
    rows.find((r) => r.project?.id === projectId)?.project?.name ??
    projectId;

  const kindOptions: FilterOption[] = GROUPS.flatMap((group) =>
    MAIL_TEMPLATE_GROUPS[group].map((template) => ({
      value: template,
      label: templateLabel(template),
      group: t(`group.${group}`),
    })),
  );
  const statusOptions: FilterOption[] = MAIL_STATUSES.map((s) => ({
    value: s,
    label: t(`statusFilter.${s}`),
  }));

  /** Выбранное условие строкой под панелью; крестик снимает поиск или названные фильтры. */
  const chip = (
    id: string,
    label: string,
    value: string,
    clear: "q" | Partial<Record<MailLogFilterName, null>>,
  ): ActiveFilter => ({
    id,
    label,
    value,
    onRemove: () => {
      if (clear === "q") state.setQ("");
      else state.setFilters(clear);
    },
  });
  const active: ActiveFilter[] = [
    ...(state.q ? [chip("q", t("filter.search"), state.q, "q")] : []),
    ...(state.filters.template.length > 0
      ? [
          chip(
            "template",
            t("filter.kind"),
            state.filters.template.map(templateLabel).join(", "),
            { template: null },
          ),
        ]
      : []),
    ...(state.filters.status.length > 0
      ? [
          chip(
            "status",
            t("filter.status"),
            state.filters.status.map((s) => t(`statusFilter.${s}`)).join(", "),
            { status: null },
          ),
        ]
      : []),
    ...(state.filter("reason")
      ? [
          chip(
            "reason",
            t("filter.reason"),
            reasonText(state.filter("reason")),
            { reason: null },
          ),
        ]
      : []),
    ...(recipientId
      ? [
          chip(
            "recipient_id",
            t("filter.recipient"),
            shownPerson ?? recipientId,
            { recipient_id: null },
          ),
        ]
      : []),
    ...(state.filter("recipient")
      ? [
          chip("recipient", t("filter.address"), state.filter("recipient"), {
            recipient: null,
          }),
        ]
      : []),
    ...(projectId
      ? [
          chip("project_id", t("filter.project"), shownProject ?? projectId, {
            project_id: null,
          }),
        ]
      : []),
    ...(periodLabel
      ? [
          chip("period", t("filter.period"), periodLabel, {
            from: null,
            to: null,
          }),
        ]
      : []),
  ];

  const columns = useMemo<ColumnDef<MailLogEntry>[]>(
    () => [
      {
        id: "at",
        header: t("col.at"),
        meta: { card: "line" },
        cell: ({ row }) => {
          const when = mailWhen(row.original.at, now, locale);
          if (!when) return <span className="ml-muted">{row.original.at}</span>;
          const text =
            when.day === "today"
              ? when.time
              : when.day === "yesterday"
                ? t("time.yesterday", { time: when.time })
                : `${when.date}, ${when.time}`;
          return (
            <time
              className="ml-time"
              dateTime={row.original.at}
              title={when.full}
            >
              {text}
            </time>
          );
        },
      },
      {
        id: "to",
        header: t("col.to"),
        meta: { card: "line" },
        cell: ({ row }) => {
          const { to_email: email, to_user: person } = row.original;
          return (
            <span className="ml-cell" title={email}>
              <span className="ml-title ml-ellipsis">{email}</span>
              {person && (
                <span className="ml-sub ml-ellipsis">{person.name}</span>
              )}
            </span>
          );
        },
      },
      {
        id: "mail",
        header: t("col.mail"),
        meta: { card: "title" },
        cell: ({ row }) => {
          const e = row.original;
          return (
            <span className="ml-cell" data-testid={`mail-row-${String(e.id)}`}>
              <span
                className="ml-title ml-ellipsis"
                data-gone={e.template_known ? undefined : "true"}
              >
                {templateLabel(e.template)}
              </span>
              <span className="ml-sub ml-ellipsis" title={e.subject}>
                {e.subject}
              </span>
            </span>
          );
        },
      },
      {
        id: "status",
        header: t("col.status"),
        meta: { card: "badges" },
        cell: ({ row }) => {
          const e = row.original;
          const why = outcomeReason(e);
          return (
            <span
              className="ml-status"
              data-testid={`mail-status-${String(e.id)}`}
            >
              <Badge variant={STATUS_BADGE[e.status]}>
                {t(`status.${e.status}`)}
              </Badge>
              {why && (
                <span className="ml-sub ml-ellipsis" title={why}>
                  {e.failure?.smtp_code != null
                    ? `${String(e.failure.smtp_code)} · ${why}`
                    : why}
                </span>
              )}
            </span>
          );
        },
      },
      {
        id: "cause",
        header: t("col.cause"),
        meta: { card: "hidden" },
        cell: ({ row }) => {
          const e = row.original;
          if (e.cause === "user" && e.actor) {
            return (
              <PersonCell
                size="sm"
                id={e.actor.id}
                name={e.actor.name}
                email={e.actor.email}
              />
            );
          }
          const Icon =
            e.cause === "system" ? Cpu : e.cause === "anonymous" ? Globe : User;
          const label =
            e.cause === "system"
              ? t("cause.system")
              : e.cause === "anonymous"
                ? t("cause.anonymous")
                : t("cause.userGone");
          const task =
            e.cause === "system" && e.task
              ? i18n.exists(`cause.task.${e.task}`, { ns: "adminMail" })
                ? t(`cause.task.${e.task}`)
                : e.task
              : null;
          return (
            <span className="ml-cause">
              <span className="ml-cause-icon" aria-hidden="true">
                <Icon size="0.6875rem" />
              </span>
              <span className="ml-cell">
                <span className="ml-muted ml-ellipsis">{label}</span>
                {task && <span className="ml-sub ml-ellipsis">{task}</span>}
              </span>
            </span>
          );
        },
      },
    ],
    [t, i18n, now, locale, templateLabel, outcomeReason],
  );

  const failedDay = (): void => {
    state.setFilters({
      status: ["failed"],
      from: isoDay(new Date(now - 24 * 3600 * 1000)),
      to: null,
    });
  };

  return (
    <div className="ml-page" data-testid="mail-log">
      <PageHeader
        title={t("title")}
        description={
          <>
            {summary
              ? t("lead", { days: summary.retention_days })
              : t("leadShort")}{" "}
            <Link
              to={RETENTION_PATH}
              className="ml-link"
              data-testid="mail-retention"
            >
              {t("retentionLink")}
            </Link>
          </>
        }
        actions={
          <Button
            variant="ghost"
            size="sm"
            type="button"
            disabled={refreshing}
            onClick={onRefresh}
            data-testid="mail-refresh"
          >
            {refreshing ? (
              <Spinner size="sm" />
            ) : (
              <RefreshCw size="0.8125rem" aria-hidden="true" />
            )}
            {t("refresh")}
          </Button>
        }
      />
      {summary && !summary.smtp_configured && (
        <div data-testid="mail-smtp-off">
          <Notice
            tone="warn"
            text={t("smtpOff.text")}
            action={
              <Link
                to={SMTP_SETTINGS_PATH}
                className="btn ghost sm ml-notice-action"
                data-testid="mail-smtp-setup"
              >
                {t("smtpOff.action")}
              </Link>
            }
          />
        </div>
      )}
      {summary && <MailDayBand summary={summary} onFailed={failedDay} />}
      <FilterBar
        search={state.q}
        onSearchChange={state.setQ}
        searchLabel={t("filter.searchLabel")}
        searchPlaceholder={t("filter.search")}
        busy={loading && rows.length > 0}
        onReset={state.reset}
        active={active}
        extra={
          <>
            <FilterMenu
              label={t("filter.kind")}
              icon={<Mail size="0.8125rem" aria-hidden="true" />}
              testId="mail-filter-kind"
              values={state.filters.template}
              onChange={(values) => {
                state.setFilter("template", values);
              }}
              options={kindOptions}
            />
            <FilterMenu
              label={t("filter.status")}
              testId="mail-filter-status"
              values={state.filters.status}
              onChange={(values) => {
                state.setFilter("status", values);
              }}
              options={statusOptions}
            />
            <PickerFilter
              label={t("filter.recipient")}
              testId="mail-filter-recipient"
              source={PEOPLE}
              value={recipientId}
              searchPlaceholder={t("filter.recipientSearch")}
              onChange={(item: PickerItem | null) => {
                state.setFilters({
                  recipient_id: item?.id ?? null,
                  recipient: null,
                });
              }}
            />
            <PickerFilter
              label={t("filter.project")}
              testId="mail-filter-project"
              source={PROJECTS}
              icon={<FolderOpen size="0.8125rem" aria-hidden="true" />}
              value={projectId}
              searchPlaceholder={t("filter.projectSearch")}
              onChange={(item: PickerItem | null) => {
                state.setFilter("project_id", item?.id ?? null);
              }}
            />
            <DateRangeFilter
              testId="mail-filter-period"
              value={period}
              onChange={({ from, to }) => {
                state.setFilters({ from, to });
              }}
            />
          </>
        }
      />
      <DataTable
        className="ml-table"
        caption={t("caption")}
        columns={columns}
        data={rows as MailLogEntry[]}
        getRowId={(row) => String(row.id)}
        loading={loading}
        error={failed ? t("loadFailed") : null}
        onRetry={onRetry}
        pagination={{
          ...pagination,
          pageSize: state.pageSize,
          pageSizes: state.pageSizes,
          onPageSizeChange: state.setPageSize,
        }}
        filtered={state.isFiltered}
        searchQuery={state.searchOnly}
        onResetFilters={state.reset}
        emptyTitle={t("empty.title")}
        emptyHint={t("empty.body")}
        emptyIcon={<Mail size="1.125rem" />}
        columnWidths={COLUMN_WIDTHS}
        selectedRowId={selectedId === null ? null : String(selectedId)}
        onRowClick={onOpen}
        skeletonRows={8}
      />
      {failedMore && (
        <ErrorState
          compact
          title={t("loadFailed")}
          retrying={pagination.loading}
          onRetry={onRetryMore ?? onRetry}
          testId="mail-more-failed"
        />
      )}
    </div>
  );
};

/** Полоса за сутки (4.1): «Отправлено», «Не ушло» (кликом фильтр), «Не отправлялось» и подсказка. */
export const MailDayBand = ({
  summary,
  onFailed,
}: {
  summary: MailLogSummary;
  onFailed: () => void;
}) => {
  const { t } = useTranslation("adminMail");
  const n = (value: number) => value.toLocaleString(localeTag());
  const hint = mailHintOf(summary);
  return (
    <div className="ml-band" data-testid="mail-day">
      <div className="ml-day">
        <span className="ml-day-caption">{t("day.caption")}</span>
        <span className="ml-day-item" data-testid="mail-day-sent">
          <span className="ml-dot" data-tone="ok" aria-hidden="true" />
          {t("day.sent", { n: n(summary.sent) })}
        </span>
        {summary.failed > 0 ? (
          <button
            type="button"
            className="ml-day-item ml-day-failed"
            data-testid="mail-day-failed"
            title={t("day.failedShow")}
            onClick={onFailed}
          >
            <span className="ml-dot" data-tone="err" aria-hidden="true" />
            {t("day.failed", { n: n(summary.failed) })}
          </button>
        ) : (
          <span className="ml-day-item" data-testid="mail-day-failed">
            <span className="ml-dot" data-tone="muted" aria-hidden="true" />
            {t("day.failed", { n: n(summary.failed) })}
          </span>
        )}
        <span className="ml-day-item" data-testid="mail-day-skipped">
          <span className="ml-dot" data-tone="muted" aria-hidden="true" />
          {t("day.skipped", { n: n(skippedCount(summary)) })}
        </span>
      </div>
      {hint && (
        <div data-testid="mail-hint" data-hint={hint}>
          <Notice
            tone="warn"
            text={t(`hint.${hint}`)}
            action={
              <Link
                to={SMTP_SETTINGS_PATH}
                className="btn ghost sm ml-notice-action"
                data-testid="mail-hint-open"
              >
                {t("hint.open")}
              </Link>
            }
          />
        </div>
      )}
    </div>
  );
};
