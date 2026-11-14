import { useState, type ComponentType, type ReactNode } from "react";
import {
  Cpu,
  Filter,
  Globe,
  Mail,
  MailX,
  RotateCw,
  User,
  X,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { localeTag } from "@shared/lib";
import {
  Badge,
  Button,
  CopyField,
  EmptyState,
  ErrorState,
  Notice,
  Spinner,
  type NoticeTone,
} from "@shared/ui";
import type { MailLogDetail, MailLogEntry } from "../api/schemas";
import {
  MAIL_MAX_ATTEMPTS,
  isMailRetrying,
  isSmtpSettingsFailure,
  mailDuration,
  mailFailureOf,
  mailNextSteps,
  type MailNextStep,
} from "../lib/mailLog";
import { mailWhen } from "../lib/when";
import {
  statusBadgeOf,
  useBlockedText,
  useReasonText,
  useTemplateLabel,
} from "./labels";
import { SMTP_SETTINGS_PATH } from "./MailLogView";
import "./mailLog.css";

/** Состояние карточки: письмо пришло, грузится, удалено по сроку (404) или ошибка. */
export type MailLogCardState = "ready" | "loading" | "not_found" | "error";

export type MailLogCardViewProps = {
  /** Сведения письма: из ответа сервера или строка списка, пока карточка грузится. */
  entry: MailLogEntry | null;
  /** Ответ `GET /mail-log/{id}`: превью и пометки; null, пока не пришёл. */
  detail: MailLogDetail | null;
  state: MailLogCardState;
  /** Сейчас, мс: полная дата попытки. */
  now: number;
  retrying?: boolean | undefined;
  onRetry: () => void;
  onClose: () => void;
  /** «Показать все письма этому адресату»: фильтр по человеку или точному адресу. */
  onShowRecipient: (entry: MailLogEntry) => void;
  /** Название проекта: фильтр журнала по проекту. */
  onShowProject: (projectId: string) => void;
  /** Заголовок окна: в панели это Dialog.Title, в галерее обычный h2. */
  Title?: ComponentType<{ className?: string; children?: ReactNode }>;
  /** «Отправить ещё раз» (14, V1); без обработчика кнопки нет. */
  onResend?: (() => void) | undefined;
  /** Идёт повтор письма. */
  resending?: boolean | undefined;
  /** Итог последнего повтора плашкой над сведениями. */
  resendNotice?: MailResendNotice | null | undefined;
  /** Открыть другое письмо журнала: исходное или его повтор. */
  onOpenEntry?: ((id: number) => void) | undefined;
};

/** Итог «Отправить ещё раз» для плашки карточки. */
export type MailResendNotice = { tone: NoticeTone; text: string };

const PlainTitle = ({
  className,
  children,
}: {
  className?: string;
  children?: ReactNode;
}) => <h2 className={className}>{children}</h2>;

const userPath = (id: string): string =>
  `/admin/users?user=${encodeURIComponent(id)}`;

const capitalize = (text: string): string =>
  text.charAt(0).toUpperCase() + text.slice(1);

/**
 * Карточка письма (docs/design/mail-log.md, 4.2): шапка с видом, темой и итогом, итог сбоя или
 * пропуска, сведения, письмо глазами получателя в песочнице с пометками и «Что можно сделать».
 * Только содержимое: панель справа или шторку на телефоне рисует MailLogCard.
 */
export const MailLogCardView = ({
  entry,
  detail,
  state,
  now,
  retrying = false,
  onRetry,
  onClose,
  onShowRecipient,
  onShowProject,
  Title = PlainTitle,
  onResend,
  resending = false,
  resendNotice = null,
  onOpenEntry,
}: MailLogCardViewProps) => {
  const { t } = useTranslation("adminMail");
  const templateLabel = useTemplateLabel();

  const close = (
    <button
      type="button"
      className="icon-btn ml-card-close"
      aria-label={t("card.close")}
      data-testid="mail-card-close"
      onClick={onClose}
    >
      <X size="1rem" aria-hidden="true" />
    </button>
  );

  if (state === "not_found" || entry === null) {
    return (
      <>
        <div className="ml-card-head">
          <div className="ml-card-heading">
            <Title className="ml-card-title">{t("card.title")}</Title>
          </div>
          {close}
        </div>
        <div className="ml-card-body" data-testid="mail-card-state">
          {state === "not_found" ? (
            <EmptyState
              icon={<MailX size="1.125rem" />}
              title={t("card.notFound.title")}
              description={t("card.notFound.body")}
              testId="mail-card-not-found"
            />
          ) : state === "error" ? (
            <ErrorState
              title={t("card.previewFailed")}
              description={t("loadFailedBody")}
              retrying={retrying}
              onRetry={onRetry}
              testId="mail-card-error"
            />
          ) : (
            <div className="ml-card-loading" data-testid="mail-card-loading">
              <Spinner />
            </div>
          )}
        </div>
      </>
    );
  }

  const when = mailWhen(entry.at, now, localeTag());
  const full = when?.full ?? entry.at;
  const badge = statusBadgeOf(entry);
  const canResend = detail?.resend.allowed === true && onResend !== undefined;

  return (
    <>
      <div className="ml-card-head">
        <div className="ml-card-heading">
          <p
            className="ml-card-kind"
            data-gone={entry.template_known ? undefined : "true"}
          >
            <Mail size="0.75rem" aria-hidden="true" />
            <span>{templateLabel(entry.template)}</span>
          </p>
          <Title className="ml-card-title">{entry.subject}</Title>
          <div className="ml-card-badges">
            <Badge variant={badge.variant} data-testid="mail-card-badge">
              {t(badge.key)}
            </Badge>
            <time
              className="ml-card-when"
              dateTime={entry.at}
              data-testid="mail-card-when"
            >
              {entry.status === "sent"
                ? t("card.sentAt", { when: full })
                : t("card.triedAt", { when: full })}
            </time>
          </div>
        </div>
        {close}
      </div>
      <div className="ml-card-body">
        {resendNotice && (
          <div data-testid="mail-card-resend-notice">
            <Notice tone={resendNotice.tone} text={resendNotice.text} />
          </div>
        )}
        {entry.status !== "sent" && (
          <Outcome
            entry={entry}
            now={now}
            resend={
              canResend ? (
                <Button
                  variant="secondary"
                  size="sm"
                  type="button"
                  className="ml-card-settings"
                  disabled={resending}
                  title={t("resend.hint")}
                  onClick={onResend}
                  data-testid="mail-card-resend"
                >
                  {resending ? (
                    <Spinner size="sm" />
                  ) : (
                    <RotateCw size="0.8125rem" aria-hidden="true" />
                  )}
                  {t("resend.button")}
                </Button>
              ) : null
            }
          />
        )}
        <Facts
          entry={entry}
          detail={detail}
          now={now}
          onShowRecipient={onShowRecipient}
          onShowProject={onShowProject}
          onOpenEntry={onOpenEntry}
        />
        <Preview
          detail={detail}
          state={state}
          retrying={retrying}
          onRetry={onRetry}
        />
        <NextSteps entry={entry} blocked={detail?.resend.blocked ?? null} />
      </div>
    </>
  );
};

/** Итог сбоя или пропуска: причина, ответ SMTP, автоповтор, ссылка в настройки почты, повтор. */
const Outcome = ({
  entry,
  now,
  resend,
}: {
  entry: MailLogEntry;
  now: number;
  resend: ReactNode;
}) => {
  const { t } = useTranslation("adminMail");
  const reasonText = useReasonText();
  const failed = entry.status === "failed";
  const why = failed
    ? t(`failure.${mailFailureOf(entry.reason)}`)
    : entry.reason
      ? capitalize(reasonText(entry.reason))
      : null;
  const reply = failed
    ? [
        entry.failure?.smtp_code == null
          ? null
          : String(entry.failure.smtp_code),
        entry.failure?.text ?? null,
      ]
        .filter((part): part is string => part !== null && part !== "")
        .join(" ")
    : "";
  const retrying = isMailRetrying(entry);
  const next = entry.next_attempt_at
    ? mailWhen(entry.next_attempt_at, now, localeTag())
    : null;
  const retry = retrying
    ? t("card.retryPlanned", {
        when: next ? t("retryAt", { time: next.time }) : entry.next_attempt_at,
        next: entry.attempts + 1,
        max: MAIL_MAX_ATTEMPTS,
      })
    : failed && entry.attempts > 1
      ? t("card.gaveUp", { n: entry.attempts })
      : null;
  return (
    <section
      className="ml-card-section"
      data-testid="mail-card-outcome"
      data-status={entry.status}
    >
      <h3 className="ml-card-caption">{t("card.outcome")}</h3>
      <div
        className="ml-card-outcome"
        data-tone={retrying ? "warn" : failed ? "err" : "muted"}
      >
        {why && (
          <p className="ml-card-why" data-testid="mail-card-reason">
            {why}
          </p>
        )}
        {reply && (
          <div className="ml-card-reply">
            <span className="ml-card-label">{t("card.smtpReply")}</span>
            <CopyField
              className="ml-copy"
              value={reply}
              label={t("card.smtpReply")}
              // Короткий ответ в одну строку, длинный (до 300 символов) целиком.
              multiline={reply.length > 64}
            />
          </div>
        )}
        {retry && (
          <p className="ml-card-retry" data-testid="mail-card-retry">
            {retry}
          </p>
        )}
        {failed && isSmtpSettingsFailure(entry.reason) && (
          <Link
            to={SMTP_SETTINGS_PATH}
            className="btn sm ml-card-settings"
            data-testid="mail-card-settings"
          >
            {t("hint.open")}
          </Link>
        )}
        {resend}
      </div>
    </section>
  );
};

/** Сведения: кому, вид, язык, кто вызвал, сценарий, проект и объект, Message-ID. */
const Facts = ({
  entry,
  detail,
  now,
  onShowRecipient,
  onShowProject,
  onOpenEntry,
}: {
  entry: MailLogEntry;
  detail: MailLogDetail | null;
  now: number;
  onShowRecipient: (entry: MailLogEntry) => void;
  onShowProject: (projectId: string) => void;
  onOpenEntry: ((id: number) => void) | undefined;
}) => {
  const { t, i18n } = useTranslation("adminMail");
  const templateLabel = useTemplateLabel();
  const label = (prefix: string, code: string): string =>
    i18n.exists(`${prefix}.${code}`, { ns: "adminMail" })
      ? t(`${prefix}.${code}`)
      : code;
  const duration = mailDuration(entry.duration_ms);
  const n = duration.value.toLocaleString(localeTag());
  const fullAt = (iso: string): string =>
    mailWhen(iso, now, localeTag())?.full ?? iso;
  const entryLink = (id: number, text: string, testId: string): ReactNode =>
    onOpenEntry ? (
      <button
        type="button"
        className="ml-card-linkish"
        data-testid={testId}
        onClick={() => {
          onOpenEntry(id);
        }}
      >
        {text}
      </button>
    ) : (
      <span data-testid={testId}>{text}</span>
    );
  const resent = detail?.resent ?? [];

  const cause = (() => {
    if (entry.cause === "user" && entry.actor) {
      return (
        <Link
          to={userPath(entry.actor.id)}
          className="ml-link"
          title={t("card.openUser")}
          data-testid="mail-card-actor"
        >
          {entry.actor.name}
        </Link>
      );
    }
    const Icon =
      entry.cause === "system"
        ? Cpu
        : entry.cause === "anonymous"
          ? Globe
          : User;
    const text =
      entry.cause === "system"
        ? entry.task
          ? t("card.systemTask", { task: label("cause.task", entry.task) })
          : t("cause.system")
        : entry.cause === "anonymous"
          ? t("cause.anonymous")
          : t("cause.userGone");
    return (
      <span className="ml-card-cause" data-testid="mail-card-actor">
        <Icon size="0.75rem" aria-hidden="true" />
        <span>{text}</span>
      </span>
    );
  })();

  return (
    <section className="ml-card-section" data-testid="mail-card-facts">
      <h3 className="ml-card-caption">{t("card.facts")}</h3>
      <dl className="ml-kv">
        <dt>{t("card.to")}</dt>
        <dd data-testid="mail-card-to">
          <span className="ml-card-email">{entry.to_email}</span>
          {entry.to_user && (
            <Link
              to={userPath(entry.to_user.id)}
              className="ml-link ml-card-person"
              title={t("card.openUser")}
            >
              {entry.to_user.name}
            </Link>
          )}
          <button
            type="button"
            className="ml-card-filter"
            data-testid="mail-card-show-all"
            onClick={() => {
              onShowRecipient(entry);
            }}
          >
            <Filter size="0.6875rem" aria-hidden="true" />
            {t("card.showAll")}
          </button>
        </dd>
        <dt>{t("card.kind")}</dt>
        <dd>{templateLabel(entry.template)}</dd>
        <dt>{t("card.lang")}</dt>
        <dd>{entry.lang.toUpperCase()}</dd>
        <dt>{t("card.cause")}</dt>
        <dd>{cause}</dd>
        <dt>{t("card.origin")}</dt>
        <dd data-testid="mail-card-origin">{label("origin", entry.origin)}</dd>
        {entry.project && (
          <>
            <dt>{t("card.project")}</dt>
            <dd data-testid="mail-card-project">
              {entry.project.name === null ? (
                <span className="ml-muted">{t("card.projectGone")}</span>
              ) : (
                <button
                  type="button"
                  className="ml-card-linkish"
                  title={t("card.projectShow")}
                  onClick={() => {
                    if (entry.project) onShowProject(entry.project.id);
                  }}
                >
                  {entry.project.name}
                </button>
              )}
            </dd>
          </>
        )}
        {entry.ref && (
          <>
            <dt>{t("card.ref")}</dt>
            <dd>{label("ref", entry.ref.kind)}</dd>
          </>
        )}
        {entry.message_id && (
          <>
            <dt>{t("card.messageId")}</dt>
            <dd data-testid="mail-card-message-id">
              <CopyField
                className="ml-copy"
                value={entry.message_id}
                label={t("card.messageId")}
              />
            </dd>
          </>
        )}
        <dt>{t("card.attempts")}</dt>
        <dd className="ml-num" data-testid="mail-card-attempts">
          {isMailRetrying(entry)
            ? t("card.attemptsOf", {
                n: entry.attempts,
                max: MAIL_MAX_ATTEMPTS,
              })
            : entry.attempts}
        </dd>
        {entry.last_attempt_at && (
          <>
            <dt>{t("card.lastAttempt")}</dt>
            <dd data-testid="mail-card-last-attempt">
              {fullAt(entry.last_attempt_at)}
            </dd>
          </>
        )}
        {entry.resent_from_id !== null && (
          <>
            <dt>{t("card.resentFrom")}</dt>
            <dd>
              {entryLink(
                entry.resent_from_id,
                `№ ${String(entry.resent_from_id)}`,
                "mail-card-resent-from",
              )}
            </dd>
          </>
        )}
        {resent.length > 0 && (
          <>
            <dt>{t("card.resent")}</dt>
            <dd>
              <ul className="ml-card-resent" data-testid="mail-card-resent">
                {resent.map((r) => (
                  <li key={r.id}>
                    {entryLink(
                      r.id,
                      t("card.resentItem", {
                        when: fullAt(r.at),
                        status: t(`status.${r.status}`).toLowerCase(),
                      }),
                      `mail-card-resent-${String(r.id)}`,
                    )}
                  </li>
                ))}
              </ul>
            </dd>
          </>
        )}
        <dt>{t("card.duration")}</dt>
        <dd className="ml-num">
          {duration.unit === "ms"
            ? t("card.ms", { n })
            : t("card.seconds", { n })}
        </dd>
      </dl>
    </section>
  );
};

/**
 * Письмо глазами получателя: пометки и HTML в iframe без скриптов и доступа к странице, как в
 * блоке «Как выглядят письма»; текстовая часть раскрывается по кнопке.
 */
const Preview = ({
  detail,
  state,
  retrying,
  onRetry,
}: {
  detail: MailLogDetail | null;
  state: MailLogCardState;
  retrying: boolean;
  onRetry: () => void;
}) => {
  const { t } = useTranslation("adminMail");
  const [showText, setShowText] = useState(false);
  const preview = detail?.preview ?? null;
  return (
    <section className="ml-card-section" data-testid="mail-card-preview">
      <h3 className="ml-card-caption">{t("card.preview")}</h3>
      {detail === null ? (
        state === "error" ? (
          <ErrorState
            compact
            title={t("card.previewFailed")}
            retrying={retrying}
            onRetry={onRetry}
            testId="mail-card-error"
          />
        ) : (
          <div className="ml-card-loading" data-testid="mail-card-loading">
            <Spinner />
          </div>
        )
      ) : (
        <>
          <div className="ml-card-notes">
            {detail.link_hidden && (
              <div data-testid="mail-card-link-hidden">
                <Notice tone="info" text={t("card.linkHidden")} />
              </div>
            )}
            {detail.rerendered && (
              <div data-testid="mail-card-rerendered">
                <Notice tone="info" text={t("card.rerendered")} />
              </div>
            )}
            {detail.note_hidden && (
              <div data-testid="mail-card-note-hidden">
                <Notice tone="info" text={t("card.noteHidden")} />
              </div>
            )}
            {preview === null && (
              <div data-testid="mail-card-template-gone">
                <Notice tone="info" text={t("card.templateGone")} />
              </div>
            )}
          </div>
          {preview && (
            <>
              <iframe
                className="ml-card-frame"
                title={t("card.frame")}
                data-testid="mail-card-frame"
                // Без allow-scripts и allow-same-origin: письмо не может ни выполнить код, ни дотянуться до страницы.
                sandbox=""
                srcDoc={preview.html}
              />
              <button
                type="button"
                className="ml-card-linkish ml-card-toggle"
                aria-expanded={showText}
                data-testid="mail-card-text-toggle"
                onClick={() => {
                  setShowText((v) => !v);
                }}
              >
                {showText ? t("card.hideText") : t("card.showText")}
              </button>
              {showText && (
                <pre className="mono ml-card-text" data-testid="mail-card-text">
                  {preview.text}
                </pre>
              )}
            </>
          )}
        </>
      )}
    </section>
  );
};

/** «Что можно сделать» по итогу и виду письма (4.2, L6). */
const NextSteps = ({
  entry,
  blocked,
}: {
  entry: MailLogEntry;
  blocked: string | null;
}) => {
  const { t } = useTranslation("adminMail");
  const reasonText = useReasonText();
  const blockedText = useBlockedText();
  const steps = mailNextSteps(entry, blocked);
  if (steps.length === 0) return null;
  const line = (step: MailNextStep): ReactNode => {
    switch (step.kind) {
      case "retrying":
        return t("card.next.retrying");
      case "stale":
        return t("card.next.stale", { reason: blockedText(step.code) });
      case "checkSmtp":
        return (
          <Link
            to={SMTP_SETTINGS_PATH}
            className="ml-link"
            data-testid="mail-card-check-smtp"
          >
            {t("card.next.checkSmtp")}
          </Link>
        );
      case "smtpOff":
        return (
          <>
            {t("card.next.smtpOff")}{" "}
            <Link to={SMTP_SETTINGS_PATH} className="ml-link">
              {t("card.next.setupSmtp")}
            </Link>
          </>
        );
      case "suppressed":
        return t("card.next.suppressed", {
          reason: step.reason ? reasonText(step.reason) : "",
        });
      case "template":
        return t(`card.next.${step.key}`);
    }
  };
  return (
    <section className="ml-card-section" data-testid="mail-card-next">
      <h3 className="ml-card-caption">{t("card.next.title")}</h3>
      <ul className="ml-card-next">
        {steps.map((step) => (
          <li
            key={step.kind === "template" ? step.key : step.kind}
            data-step={
              step.kind === "template"
                ? step.key
                : step.kind === "stale"
                  ? `stale:${step.code}`
                  : step.kind
            }
          >
            {line(step)}
          </li>
        ))}
      </ul>
    </section>
  );
};
