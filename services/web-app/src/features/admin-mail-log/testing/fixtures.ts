import {
  isKnownMailTemplate,
  type MailCause,
  type MailLang,
  type MailLogDetail,
  type MailLogEntry,
  type MailLogPage,
  type MailLogPerson,
  type MailLogPreview,
  type MailLogProject,
  type MailLogRef,
  type MailLogSummary,
  type MailStatus,
  type MailTemplate,
} from "../api/schemas";
import {
  MAIL_LOG_SERVER_DETAILS,
  MAIL_LOG_SERVER_PAGES,
  MAIL_LOG_SERVER_SUMMARIES,
} from "./serverFixtures";

// Журнал писем для галерей, демо-мира и тестов экранов (docs/design/mail-log.md, 4.4 и 6.2).
// Журнал описан черновиками «сколько секунд назад»: галереи строят его от постоянного MAIL_NOW,
// чтобы снимки не плыли, а демо-мир от текущего времени, чтобы полоса «за сутки» была живой.
// Тела писем здесь не хранятся, как и на сервере: превью собирается из вида, языка и значений,
// ссылка с токеном скрыта, сообщение человека заменено пометкой (L3, L4).

export const MAIL_NOW = "2026-11-11T10:00:00Z";
const NOW_MS = Date.parse(MAIL_NOW);
const MIN = 60;
const HOUR = 3600;
const DAY = 86400;

/** Срок хранения по умолчанию (L12). */
export const MAIL_RETENTION_DAYS = 90;
export const MAIL_WINDOW_HOURS = 24 as const;
export const MAIL_SERVER = "studio.example.org";

// Люди и проекты те же, что в демо-мире сервера (app/demo/server: adminPeople, projects).
export const MAIL_PEOPLE = {
  admin: {
    id: "u_01hx7k1a0b",
    name: "Иван Сидоров",
    email: "ivan.sidorov@example.org",
  },
  maria: {
    id: "u_01hx7k2c1d",
    name: "Мария Келлер",
    email: "maria.keller@example.org",
  },
  petr: {
    id: "u_01hx7k3e2f",
    name: "Пётр Орлов",
    email: "petr.orlov@example.org",
  },
  volkova: {
    id: "u_01hx7k4g3h",
    name: "Анна Волкова",
    email: "anna.volkova@example.org",
  },
  /** Почта не подтверждена (pending_verification). */
  oleg: {
    id: "u_01hx7k5i4j",
    name: "Олег Миронов",
    email: "oleg.mironov@example.org",
  },
  /** Вход закрыт (disabled). */
  darya: {
    id: "u_01hx7k6k5l",
    name: "Дарья Лис",
    email: "darya.lis@example.org",
  },
  elena: {
    id: "u_01hx7k3e5f",
    name: "Елена Миронова",
    email: "elena.mironova@example.org",
  },
  anna: {
    id: "u_01hx7k2m9c",
    name: "Анна Петрова",
    email: "anna.petrova@example.org",
  },
  olga: {
    id: "u_01hx7k5q7h",
    name: "Ольга Белова",
    email: "olga.belova@example.org",
  },
  dmitry: {
    id: "u_01hx7k6r8j",
    name: "Дмитрий Кузнецов",
    email: "dmitry.kuznetsov@example.org",
  },
} as const satisfies Record<string, MailLogPerson>;

export const MAIL_PROJECTS = {
  bertie: { id: "p_01hxa1c4de", name: "Bertie: курсовой проект" },
  ci: { id: "p_01hxa2f8gh", name: "Industry adoption of CI" },
  queue: { id: "p_01hxa3k2jm", name: "Анализ нагрузки на очередь задач" },
  practice: { id: "p_01hxa4n7pq", name: "Практика 2025: отчёт" },
  /** Проект удалён: строка журнала его переживает, названия уже нет (L9). */
  gone: { id: "p_01hxa9zz00", name: null },
} as const satisfies Record<string, MailLogProject>;

/** Как в письме была ссылка (5.2): с токеном, адрес страницы без токена, никакой. */
export type MailLinkKind = "token" | "page" | "none";

/**
 * Строка журнала, как её хранит демо-сервер: сведения строки и то, что сервер держит в `params`
 * (вид ссылки, путь страницы, было ли сообщение) и признак перерисовки по новому шаблону.
 */
export type MailLogRecord = {
  entry: MailLogEntry;
  link: MailLinkKind;
  /** Путь страницы без адреса сервера, только у `page`. */
  link_path: string | null;
  /** Длина сообщения человека; текст не хранится. */
  note_len: number;
  /** Безопасные значения шаблона (белый список L3). */
  values: Readonly<Record<string, string>>;
  rerendered: boolean;
  /** Тема перерисовки, если она отличается от ушедшей (после правки шаблона). */
  preview_subject: string | null;
  /** Письмо уже неактуально по объекту (14.2): код причины, как его даст сервер. */
  stale: string | null;
};

/** Черновик строки: время задано «сколько секунд назад», остальное по умолчанию. */
export type MailDraft = {
  ago: number;
  template: string;
  lang?: MailLang;
  to: MailLogPerson | string;
  /** Адрес, если он не основной адрес человека (смена e-mail шлёт на новый). */
  to_email?: string;
  subject: string;
  status: MailStatus;
  reason?: string;
  smtp_code?: number;
  error?: string;
  duration_ms?: number;
  cause: MailCause;
  actor?: MailLogPerson;
  task?: string;
  origin: string;
  project?: MailLogProject;
  ref?: MailLogRef;
  link?: MailLinkKind;
  link_path?: string;
  note_len?: number;
  values?: Record<string, string>;
  rerendered?: boolean;
  preview_subject?: string;
  /** Попыток (автоповтор, 14, V7); по умолчанию 1. */
  attempts?: number;
  /** Автоповтор запланирован через столько секунд от «сейчас». */
  next_in?: number;
  /** Последняя попытка столько секунд назад (если попыток больше одной). */
  last_ago?: number;
  /** Ручной повтор строки с этим id. */
  resent_from_id?: number;
  /** Письмо уже неактуально по объекту: код причины (14.2). */
  stale?: string;
};

const isoAt = (ms: number): string =>
  new Date(ms).toISOString().replace(".000Z", "Z");

const messageIdOf = (id: number, ms: number): string =>
  `<${String(Math.floor(ms / 1000))}.${String(id)}@${MAIL_SERVER}>`;

const durationOf = (draft: MailDraft): number => {
  if (draft.duration_ms !== undefined) return draft.duration_ms;
  if (draft.status === "not_sent" || draft.status === "suppressed") return 0;
  if (draft.status === "failed") return 1240;
  return 420 + (draft.template.length % 7) * 61;
};

/** Строка журнала из черновика; `id` растёт со временем, новые сверху. */
export const makeMailLogRecord = (
  draft: MailDraft,
  id: number,
  nowMs: number = NOW_MS,
): MailLogRecord => {
  const ms = nowMs - draft.ago * 1000;
  const person = typeof draft.to === "string" ? null : draft.to;
  const entry: MailLogEntry = {
    id,
    at: isoAt(ms),
    template: draft.template,
    template_known: isKnownMailTemplate(draft.template),
    lang: draft.lang ?? "ru",
    to_email:
      draft.to_email ??
      (typeof draft.to === "string" ? draft.to : (draft.to.email ?? "")),
    to_user: person ? { ...person } : null,
    subject: draft.subject,
    status: draft.status,
    reason: draft.reason ?? null,
    failure:
      draft.status === "failed"
        ? { smtp_code: draft.smtp_code ?? null, text: draft.error ?? null }
        : null,
    message_id: draft.status === "sent" ? messageIdOf(id, ms) : null,
    attempts: draft.attempts ?? 1,
    duration_ms: durationOf(draft),
    cause: draft.cause,
    actor: draft.actor ? { ...draft.actor } : null,
    task: draft.task ?? null,
    origin: draft.origin,
    project: draft.project ? { ...draft.project } : null,
    ref: draft.ref ? { ...draft.ref } : null,
    next_attempt_at:
      draft.next_in === undefined ? null : isoAt(nowMs + draft.next_in * 1000),
    last_attempt_at:
      draft.last_ago === undefined
        ? null
        : isoAt(nowMs - draft.last_ago * 1000),
    resent_from_id: draft.resent_from_id ?? null,
  };
  const link = draft.link ?? "none";
  return {
    entry,
    link,
    link_path: link === "page" ? (draft.link_path ?? "/") : null,
    note_len: draft.note_len ?? 0,
    values: draft.values ?? {},
    rerendered: draft.rerendered ?? false,
    preview_subject: draft.preview_subject ?? null,
    stale: draft.stale ?? null,
  };
};

/** Журнал из черновиков в любом порядке: id по времени, новые сверху. */
export const makeMailJournal = (
  drafts: readonly MailDraft[],
  nowMs: number = NOW_MS,
  firstId = 1,
): MailLogRecord[] =>
  [...drafts]
    .sort((a, b) => b.ago - a.ago)
    .map((draft, i) => makeMailLogRecord(draft, firstId + i, nowMs))
    .reverse();

// ── Превью ────────────────────────────────────────────────────────────────

const COPY: Record<
  MailTemplate,
  Record<MailLang, { lead: string; action: string | null }>
> = {
  verify_email: {
    ru: {
      lead: "Осталось подтвердить, что этот адрес принадлежит вам, и учётная запись в Студии заработает.",
      action: "Подтвердить адрес",
    },
    en: {
      lead: "One step left: confirm that this address is yours and your Studio account will be ready.",
      action: "Confirm address",
    },
  },
  reset_password: {
    ru: {
      lead: "Мы получили запрос на смену пароля. Нажмите кнопку, чтобы задать новый.",
      action: "Задать новый пароль",
    },
    en: {
      lead: "We received a request to change your password. Press the button to set a new one.",
      action: "Set a new password",
    },
  },
  invite: {
    ru: {
      lead: "{inviter} приглашает вас в Студию. Чтобы зарегистрироваться, нажмите кнопку.",
      action: "Зарегистрироваться",
    },
    en: {
      lead: "{inviter} invites you to the Studio. Press the button to sign up.",
      action: "Sign up",
    },
  },
  email_change: {
    ru: {
      lead: "Вы просили привязать этот адрес к учётной записи в Студии. Нажмите кнопку, чтобы подтвердить смену.",
      action: "Подтвердить новый адрес",
    },
    en: {
      lead: "You asked to attach this address to your Studio account. Press the button to confirm the change.",
      action: "Confirm new address",
    },
  },
  reset_notice: {
    ru: {
      lead: "Администратор Студии создал ссылку для сброса пароля вашей учётной записи.",
      action: null,
    },
    en: {
      lead: "A Studio administrator created a password reset link for your account.",
      action: null,
    },
  },
  passkey_added: {
    ru: {
      lead: "К вашей учётной записи в Студии добавлен passkey «{name}».",
      action: "Открыть настройки аккаунта",
    },
    en: {
      lead: "A passkey “{name}” was added to your Studio account.",
      action: "Open account settings",
    },
  },
  passkey_reset: {
    ru: {
      lead: "Администратор Студии удалил все passkey вашей учётной записи.",
      action: "Открыть настройки аккаунта",
    },
    en: {
      lead: "A Studio administrator removed all passkeys of your account.",
      action: "Open account settings",
    },
  },
  project_invitation: {
    ru: {
      lead: "{actor} приглашает вас в проект «{project}» с ролью «{role}».",
      action: "Открыть «Входящие»",
    },
    en: {
      lead: "{actor} invites you to the project “{project}” as {role}.",
      action: "Open Inbox",
    },
  },
  project_invitation_link: {
    ru: {
      lead: "{actor} приглашает вас в проект «{project}» в Студии с ролью «{role}».",
      action: "Принять приглашение",
    },
    en: {
      lead: "{actor} invites you to the project “{project}” in the Studio as {role}.",
      action: "Accept invitation",
    },
  },
  access_request: {
    ru: {
      lead: "{actor} просит доступ к проекту «{project}».",
      action: "Открыть «Входящие»",
    },
    en: {
      lead: "{actor} requests access to the project “{project}”.",
      action: "Open Inbox",
    },
  },
  transfer_request: {
    ru: {
      lead: "{actor} передаёт вам проект «{project}». После принятия вы станете его владельцем.",
      action: "Открыть «Входящие»",
    },
    en: {
      lead: "{actor} is transferring the project “{project}” to you. Once you accept, you become its owner.",
      action: "Open Inbox",
    },
  },
  signing_request: {
    ru: {
      lead: "{actor} просит подписать документы «{profile}» в проекте «{project}».",
      action: "Открыть страницу подписи",
    },
    en: {
      lead: "{actor} asks you to sign the documents “{profile}” in the project “{project}”.",
      action: "Open the signing page",
    },
  },
  signing_request_sign: {
    ru: {
      lead: "Документы «{profile}» в проекте «{project}» зафиксированы. Осталось подписать итоговый PDF электронной подписью.",
      action: "Открыть страницу подписи",
    },
    en: {
      lead: "The documents “{profile}” in the project “{project}” are frozen. Only your electronic signature on the final PDF is left.",
      action: "Open the signing page",
    },
  },
  signing_request_new_version: {
    ru: {
      lead: "{actor} просит подписать новую версию документов «{profile}» в проекте «{project}».",
      action: "Открыть страницу подписи",
    },
    en: {
      lead: "{actor} asks you to sign a new version of the documents “{profile}” in the project “{project}”.",
      action: "Open the signing page",
    },
  },
  signing_reminder: {
    ru: {
      lead: "Документы «{profile}» в проекте «{project}» всё ещё ждут вашей подписи.",
      action: "Открыть страницу подписи",
    },
    en: {
      lead: "The documents “{profile}” in the project “{project}” are still waiting for your signature.",
      action: "Open the signing page",
    },
  },
  signing_skipped: {
    ru: {
      lead: "Автор маршрута пропустил ваш шаг по документам «{profile}» в проекте «{project}»: ваши подписи на этой точке необязательны. Подписывать ничего не нужно.",
      action: "Открыть страницу подписи",
    },
    en: {
      lead: "The route author skipped your step for the documents “{profile}” in the project “{project}”: your signatures at this checkpoint are optional. There is nothing to sign.",
      action: "Open the signing page",
    },
  },
  signing_returned: {
    ru: {
      lead: "Документы проекта «{project}» возвращены на доработку ({actor}). Маршрут подписания остановлен.",
      action: "Открыть маршрут",
    },
    en: {
      lead: "{actor} returned the documents of the project “{project}” for revision. The signing route is stopped.",
      action: "Open the route",
    },
  },
  signing_completed: {
    ru: {
      lead: "Все участники маршрута подписали документы «{profile}» в проекте «{project}». Можно собирать пакет.",
      action: "Открыть контрольную точку",
    },
    en: {
      lead: "All route participants signed the documents “{profile}” in the project “{project}”. You can build the package now.",
      action: "Open the checkpoint",
    },
  },
  checkpoint_due: {
    ru: {
      lead: "Срок контрольной точки «{profile}» в проекте «{project}»: {deadline}. Пакет для сдачи ещё не собран.",
      action: "Открыть контрольную точку",
    },
    en: {
      lead: "The checkpoint “{profile}” in the project “{project}” is due {deadline}. The submission package is not built yet.",
      action: "Open the checkpoint",
    },
  },
  smtp_test: {
    ru: {
      lead: "Это тестовое письмо Студии. Если вы его читаете, отправка работает.",
      action: null,
    },
    en: {
      lead: "This is a test message from the Studio. If you can read it, mail sending works.",
      action: null,
    },
  },
};

const LAYOUT: Record<
  MailLang,
  {
    fallback: string;
    linkHidden: string;
    noteTitle: string;
    noteHidden: string;
    recipient: string;
    auto: string;
  }
> = {
  ru: {
    fallback:
      "Если кнопка не открывается, скопируйте ссылку в адресную строку браузера:",
    linkHidden: "[ссылка скрыта]",
    noteTitle: "Сообщение к приглашению",
    noteHidden: "[сообщение не хранится в журнале]",
    recipient: "Письмо отправлено на адрес {email}.",
    auto: "Это автоматическое сообщение, отвечать на него не нужно.",
  },
  en: {
    fallback:
      "If the button does not open, copy this link into your browser's address bar:",
    linkHidden: "[link hidden]",
    noteTitle: "Message with the invitation",
    noteHidden: "[message not kept in the log]",
    recipient: "This email was sent to {email}.",
    auto: "This is an automated message, please do not reply.",
  },
};

const escapeHtml = (text: string): string =>
  text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");

const fill = (text: string, values: Readonly<Record<string, string>>) =>
  text.replace(/\{(\w+)\}/g, (_m, key: string) => values[key] ?? `{${key}}`);

/**
 * Превью письма из строки журнала, как его перерисует сервер в режиме `links="redacted"` (5.3):
 * кнопка без ссылки, вместо ссылки с токеном «[ссылка скрыта]», у страницы без токена её путь
 * текстом, сообщение человека заменено пометкой. null, если вида в этой версии нет.
 */
export const renderMailPreview = (
  record: MailLogRecord,
): MailLogPreview | null => {
  const { entry } = record;
  if (!isKnownMailTemplate(entry.template)) return null;
  const lang = entry.lang;
  const copy = COPY[entry.template][lang];
  const layout = LAYOUT[lang];
  const values = { email: entry.to_email, ...record.values };
  const subject = record.preview_subject ?? entry.subject;
  const lead = fill(copy.lead, values);
  const linkText =
    record.link === "token"
      ? layout.linkHidden
      : record.link === "page"
        ? `https://${MAIL_SERVER}${record.link_path ?? "/"}`
        : null;
  const note = record.note_len > 0 ? layout.noteHidden : null;
  const recipient = fill(layout.recipient, values);

  const text = [
    subject,
    "",
    lead,
    ...(copy.action && linkText ? ["", `${copy.action}: ${linkText}`] : []),
    ...(note ? ["", `${layout.noteTitle}:`, note] : []),
    "",
    "--",
    recipient,
    layout.auto,
  ].join("\n");

  const button = copy.action
    ? `<p style="margin:24px 0"><span style="display:inline-block;background:#1d4ed8;color:#ffffff;padding:12px 20px;border-radius:6px;font-weight:600">${escapeHtml(copy.action)}</span></p>`
    : "";
  const fallback =
    copy.action && linkText
      ? `<p style="font-size:13px;color:#4b5563">${escapeHtml(layout.fallback)}<br><span style="color:#1f2933">${escapeHtml(linkText)}</span></p>`
      : "";
  const noteBlock = note
    ? `<div style="margin:16px 0;padding:12px 16px;background:#f3f4f6;border-radius:6px"><p style="margin:0 0 4px;font-size:13px;color:#4b5563">${escapeHtml(layout.noteTitle)}</p><p style="margin:0">${escapeHtml(note)}</p></div>`
    : "";
  const html = [
    `<!DOCTYPE html><html lang="${lang}"><head><meta charset="utf-8"><title>${escapeHtml(subject)}</title></head>`,
    `<body style="margin:0;background:#f4f5f7;font-family:Arial,Helvetica,sans-serif;color:#1f2933">`,
    `<div style="max-width:560px;margin:0 auto;padding:24px">`,
    `<div style="background:#ffffff;border-radius:8px;padding:32px">`,
    `<p style="margin:0 0 16px;font-size:12px;color:#6b7280">HSE Doc Studio</p>`,
    `<h1 style="margin:0 0 16px;font-size:20px">${escapeHtml(subject)}</h1>`,
    `<p style="margin:0">${escapeHtml(lead)}</p>`,
    button,
    fallback,
    noteBlock,
    `</div>`,
    `<p style="font-size:12px;color:#6b7280">${escapeHtml(recipient)}<br>${escapeHtml(layout.auto)}</p>`,
    `</div></body></html>`,
  ].join("");
  return { subject, html, text };
};

/** Окно ручного повтора от первой попытки (14, V4). */
export const MAIL_RESEND_WINDOW_HOURS = 72;

export type MailResendContext = {
  /** Журнал, где искать ручные повторы строки; по умолчанию их нет. */
  journal?: readonly MailLogRecord[];
  nowMs?: number;
  /** Настроена ли почта сейчас; по умолчанию да. */
  smtpConfigured?: boolean;
};

/** Ручные повторы строки (`resent_from_id`), новые первыми. */
export const mailResentOf = (
  record: MailLogRecord,
  journal: readonly MailLogRecord[] = [],
): MailLogDetail["resent"] =>
  journal
    .filter((r) => r.entry.resent_from_id === record.entry.id)
    .sort((a, b) => b.entry.id - a.entry.id)
    .map((r) => ({ id: r.entry.id, at: r.entry.at, status: r.entry.status }));

/** Почему «Отправить ещё раз» недоступно: те же правила и порядок, что у сервера (14.2). */
export const mailResendBlockOf = (
  record: MailLogRecord,
  context: MailResendContext = {},
): string | null => {
  const { entry } = record;
  const nowMs = context.nowMs ?? NOW_MS;
  const resent = mailResentOf(record, context.journal);
  if (entry.status !== "failed" && entry.status !== "not_sent") return "status";
  if (!entry.template_known) return "template_gone";
  if (record.link === "token") return "token_link";
  if (entry.template === "smtp_test") return "smtp_test";
  if (entry.next_attempt_at !== null) return "retrying";
  if (Date.parse(entry.at) < nowMs - MAIL_RESEND_WINDOW_HOURS * HOUR * 1000) {
    return "too_old";
  }
  if (resent.some((r) => r.status === "sent")) return "already_resent";
  if (context.smtpConfigured === false) return "smtp_off";
  return record.stale;
};

/** Карточка письма, как её отдаёт `GET /mail-log/{id}` (6.2, 14.4). */
export const makeMailLogDetail = (
  record: MailLogRecord,
  context: MailResendContext = {},
): MailLogDetail => {
  const blocked = mailResendBlockOf(record, context);
  return {
    entry: structuredClone(record.entry),
    preview: renderMailPreview(record),
    link_hidden: record.link === "token",
    note_hidden: record.note_len > 0,
    rerendered: record.entry.template_known && record.rerendered,
    resend: { allowed: blocked === null, blocked },
    resent: mailResentOf(record, context.journal),
  };
};

// ── Сводка ────────────────────────────────────────────────────────────────

/**
 * Сводка за окно `window_hours` до nowMs по строкам журнала. `last_failure` это последний
 * `failed` в том же окне: старые сбои не держат подсказку под полосой.
 */
export const makeMailLogSummary = (
  journal: readonly MailLogRecord[],
  options: { smtpConfigured: boolean; nowMs?: number; retentionDays?: number },
): MailLogSummary => {
  const nowMs = options.nowMs ?? NOW_MS;
  const since = nowMs - MAIL_WINDOW_HOURS * HOUR * 1000;
  const counts = { sent: 0, failed: 0, not_sent: 0, suppressed: 0 };
  let retrying = 0;
  let last: MailLogEntry | null = null;
  for (const { entry } of journal) {
    const at = Date.parse(entry.at);
    if (at < since || at > nowMs) continue;
    // Ждут автоповтора: в `failed` не входят (V13).
    if (entry.status === "failed" && entry.next_attempt_at !== null) {
      retrying += 1;
    } else {
      counts[entry.status] += 1;
    }
    if (
      entry.status === "failed" &&
      (last === null || at > Date.parse(last.at))
    ) {
      last = entry;
    }
  }
  return {
    smtp_configured: options.smtpConfigured,
    window_hours: MAIL_WINDOW_HOURS,
    ...counts,
    retrying,
    last_failure: last ? { at: last.at, reason: last.reason ?? "other" } : null,
    retention_days: options.retentionDays ?? MAIL_RETENTION_DAYS,
  };
};

/** Страница журнала, как её отдаёт `GET /mail-log` (6.2). */
export const makeMailLogPage = (
  journal: readonly MailLogRecord[],
  options: { nextCursor?: string | null; totalEstimate?: number | null } = {},
): MailLogPage => ({
  items: journal.map((r) => structuredClone(r.entry)),
  next_cursor: options.nextCursor ?? null,
  total_estimate:
    options.totalEstimate === undefined
      ? journal.length
      : options.totalEstimate,
});

// ── Журналы демо-мира ─────────────────────────────────────────────────────

const P = MAIL_PEOPLE;
const PR = MAIL_PROJECTS;
const SIGN_ROUTE = "sr_01hy2b7k9q";
const SIGN_PATH = `/sign/${PR.bertie.id}/${SIGN_ROUTE}`;
const QUEUE_ROUTE = "sr_01hy3c4d5e";
const QUEUE_PATH = `/sign/${PR.queue.id}/${QUEUE_ROUTE}`;
const TOPIC = "Тема и руководитель";

/**
 * Обычная установка: почта настроена, за сутки все итоги вперемешку, глубже по времени все виды
 * писем, каждый класс сбоя, вид, которого в этой версии уже нет, и неушедшее до настройки почты.
 */
export const MAIL_DEFAULT_DRAFTS: readonly MailDraft[] = [
  {
    ago: 4 * MIN,
    template: "reset_password",
    to: P.petr,
    subject: "Сброс пароля",
    status: "sent",
    cause: "anonymous",
    origin: "forgot_password",
    link: "token",
  },
  {
    ago: 12 * MIN,
    template: "signing_request",
    to: P.anna,
    subject: `Мария Келлер просит подписать: ${TOPIC}`,
    status: "sent",
    cause: "user",
    actor: P.maria,
    origin: "notification",
    project: PR.bertie,
    ref: { kind: "signing_route", id: SIGN_ROUTE },
    link: "page",
    link_path: SIGN_PATH,
    values: { actor: P.maria.name, project: PR.bertie.name, profile: TOPIC },
  },
  {
    ago: 25 * MIN,
    template: "project_invitation_link",
    to: "reject-x@example.org",
    subject: "Мария Келлер приглашает вас в «Bertie: курсовой проект»",
    status: "failed",
    reason: "recipient_refused",
    smtp_code: 550,
    error:
      "5.1.1 <reject-x@example.org>: Recipient address rejected: User unknown in virtual mailbox table",
    cause: "user",
    actor: P.maria,
    origin: "project_invite",
    project: PR.bertie,
    ref: { kind: "project_invitation", id: "pi_01hy4f6g7h" },
    link: "token",
    note_len: 64,
    values: { actor: P.maria.name, project: PR.bertie.name, role: "editor" },
  },
  {
    // Временный сбой: Студия повторит отправку сама (14, V6).
    ago: 7 * MIN,
    template: "signing_request",
    to: P.olga,
    subject: `Мария Келлер просит подписать: ${TOPIC}`,
    status: "failed",
    reason: "recipient_refused",
    smtp_code: 451,
    error:
      "4.7.1 <olga@example.org>: Recipient address rejected: Greylisted, please try again later",
    duration_ms: 380,
    attempts: 2,
    last_ago: 2 * MIN,
    next_in: 3 * MIN,
    cause: "user",
    actor: P.maria,
    origin: "notification",
    project: PR.bertie,
    ref: { kind: "signing_route", id: SIGN_ROUTE },
    link: "page",
    link_path: SIGN_PATH,
    values: { actor: P.maria.name, project: PR.bertie.name, profile: TOPIC },
  },
  {
    // Пять попыток не помогли; маршрут ещё ждёт подписи, можно отправить ещё раз.
    ago: 30 * MIN,
    template: "checkpoint_due",
    to: P.anna,
    subject: `Срок через 3 дня: ${TOPIC}`,
    status: "failed",
    reason: "timeout",
    error:
      "SMTPConnectTimeoutError: Timed out connecting to smtp.example.org on port 587",
    duration_ms: 10012,
    attempts: 5,
    last_ago: 2 * MIN,
    cause: "system",
    task: "checkpoint_reminders",
    origin: "notification",
    project: PR.bertie,
    link: "page",
    link_path: `/projects/${PR.bertie.id}/submit/cp/topic`,
    values: {
      project: PR.bertie.name,
      profile: TOPIC,
      deadline: "14 ноября 2026, 23:59 (МСК)",
    },
  },
  {
    ago: 40 * MIN,
    template: "signing_reminder",
    to: P.olga,
    subject: "Напоминание: Отчёт по практике",
    status: "sent",
    cause: "system",
    task: "signing_reminders",
    origin: "signing_auto_reminder",
    project: PR.queue,
    ref: { kind: "signing_route", id: QUEUE_ROUTE },
    link: "page",
    link_path: QUEUE_PATH,
    values: { project: PR.queue.name, profile: "Отчёт по практике" },
  },
  {
    ago: 90 * MIN,
    template: "project_invitation",
    to: P.darya,
    subject: "Пётр Орлов приглашает вас в «Практика 2025: отчёт»",
    status: "suppressed",
    reason: "account_blocked",
    cause: "user",
    actor: P.petr,
    origin: "notification",
    project: PR.practice,
    ref: { kind: "project_invitation", id: "pi_01hy4k2m3n" },
    link: "page",
    link_path: "/inbox",
    values: { actor: P.petr.name, project: PR.practice.name, role: "reader" },
  },
  {
    ago: 2 * HOUR,
    template: "verify_email",
    to: P.oleg,
    subject: "Подтвердите e-mail",
    status: "sent",
    cause: "anonymous",
    origin: "resend_verification",
    link: "token",
  },
  {
    ago: 3 * HOUR,
    template: "access_request",
    to: P.maria,
    subject: "Анна Петрова просит доступ к «Industry adoption of CI»",
    status: "sent",
    cause: "user",
    actor: P.anna,
    origin: "notification",
    project: PR.ci,
    ref: { kind: "access_request", id: "ar_01hy5a1b2c" },
    link: "page",
    link_path: "/inbox",
    values: { actor: P.anna.name, project: PR.ci.name },
  },
  {
    ago: 4 * HOUR,
    template: "transfer_request",
    lang: "en",
    to: P.admin,
    subject:
      "Пётр Орлов is transferring “Анализ нагрузки на очередь задач” to you",
    status: "failed",
    reason: "timeout",
    error: "Timed out waiting for server response",
    duration_ms: 30000,
    cause: "user",
    actor: P.petr,
    origin: "notification",
    project: PR.queue,
    ref: { kind: "transfer", id: "tr_01hy5d3e4f" },
    link: "page",
    link_path: "/inbox",
    values: { actor: P.petr.name, project: PR.queue.name },
  },
  {
    ago: 5 * HOUR,
    template: "signing_request_new_version",
    to: P.oleg,
    subject: `Мария Келлер просит подписать новую версию: ${TOPIC}`,
    status: "suppressed",
    reason: "email_unverified",
    cause: "user",
    actor: P.maria,
    origin: "notification",
    project: PR.bertie,
    ref: { kind: "signing_route", id: SIGN_ROUTE },
    link: "page",
    link_path: SIGN_PATH,
    note_len: 120,
    values: { actor: P.maria.name, project: PR.bertie.name, profile: TOPIC },
  },
  {
    ago: 7 * HOUR,
    template: "smtp_test",
    to: P.admin,
    subject: "HSE Doc Studio: проверка почты",
    status: "sent",
    cause: "user",
    actor: P.admin,
    origin: "smtp_test",
    values: { server: MAIL_SERVER },
  },
  {
    ago: 9 * HOUR,
    template: "passkey_added",
    lang: "en",
    to: P.admin,
    subject: "A passkey was added",
    status: "sent",
    cause: "user",
    actor: P.admin,
    origin: "passkey_added",
    ref: { kind: "passkey", id: "pk_01hy6a7b8c" },
    link: "page",
    link_path: "/settings/account",
    values: { name: "MacBook Touch ID" },
  },
  {
    ago: 20 * HOUR,
    template: "invite",
    to: "new.student@example.org",
    subject: "Приглашение в Студию",
    status: "sent",
    cause: "user",
    actor: P.admin,
    origin: "admin_invite",
    ref: { kind: "registration_invite", id: "inv_01hy6d9e0f" },
    link: "token",
    values: { inviter: P.admin.name },
    rerendered: true,
    preview_subject: "Вас приглашают в Студию",
  },
  {
    ago: 23 * HOUR,
    template: "signing_completed",
    to: P.maria,
    subject: `Все подписали: ${TOPIC}`,
    status: "sent",
    cause: "user",
    actor: P.olga,
    origin: "notification",
    project: PR.bertie,
    ref: { kind: "signing_route", id: SIGN_ROUTE },
    link: "page",
    link_path: SIGN_PATH,
    values: { project: PR.bertie.name, profile: TOPIC },
  },
  // ── старше суток ──
  {
    ago: DAY + 3 * HOUR,
    template: "signing_returned",
    to: P.maria,
    subject: "Документы возвращены на доработку: Пётр Орлов",
    status: "sent",
    cause: "user",
    actor: P.petr,
    origin: "notification",
    project: PR.bertie,
    ref: { kind: "signing_route", id: SIGN_ROUTE },
    link: "page",
    link_path: SIGN_PATH,
    note_len: 212,
    values: { actor: P.petr.name, project: PR.bertie.name },
  },
  {
    ago: DAY + 3 * HOUR + 30 * MIN,
    template: "checkpoint_due",
    to: P.maria,
    subject: `Скоро срок сдачи: ${TOPIC}`,
    status: "sent",
    cause: "system",
    task: "checkpoint_reminders",
    origin: "notification",
    project: PR.bertie,
    link: "page",
    link_path: `/projects/${PR.bertie.id}/submit/cp/topic-approval`,
    values: {
      project: PR.bertie.name,
      profile: TOPIC,
      deadline: "15.11.2026, 23:59 (МСК)",
      signing: "ждём научного руководителя (Иван Сидоров)",
    },
  },
  {
    ago: DAY + 4 * HOUR,
    template: "signing_skipped",
    to: P.anna,
    subject: "Ваша подпись не требуется: Заявка на тему КП",
    status: "sent",
    cause: "user",
    actor: P.maria,
    origin: "notification",
    project: PR.bertie,
    ref: { kind: "signing_route", id: SIGN_ROUTE },
    link: "page",
    link_path: SIGN_PATH,
    values: { actor: P.maria.name, project: PR.bertie.name, profile: TOPIC },
  },
  {
    ago: DAY + 6 * HOUR,
    template: "email_change",
    to: P.anna,
    to_email: "anna.petrova.hse@example.org",
    subject: "Подтвердите новый e-mail",
    status: "sent",
    cause: "user",
    actor: P.anna,
    origin: "email_change",
    link: "token",
  },
  {
    ago: DAY + 9 * HOUR,
    template: "reset_notice",
    to: P.dmitry,
    subject: "Администратор выдал ссылку для сброса пароля",
    status: "sent",
    cause: "user",
    actor: P.admin,
    origin: "admin_reset_link",
  },
  {
    ago: DAY + 12 * HOUR,
    template: "project_invitation_link",
    to: "o.belova.supervisor@gmail.com",
    subject: "Мария Келлер приглашает вас в «Bertie: курсовой проект»",
    status: "sent",
    cause: "user",
    actor: P.maria,
    origin: "project_invite",
    project: PR.bertie,
    ref: { kind: "project_invitation", id: "pi_01hy7a1b2c" },
    link: "token",
    note_len: 87,
    values: {
      actor: P.maria.name,
      project: PR.bertie.name,
      role: "reviewer",
    },
  },
  {
    ago: 2 * DAY,
    template: "passkey_reset",
    to: P.dmitry,
    subject: "Администратор сбросил ваши passkey",
    status: "sent",
    cause: "user",
    actor: P.admin,
    origin: "admin_passkeys_reset",
    link: "page",
    link_path: "/settings/account",
    values: { count: "2" },
  },
  {
    ago: 2 * DAY + 4 * HOUR,
    template: "signing_request_sign",
    to: P.petr,
    subject: `Подпишите итоговый PDF: ${TOPIC}`,
    status: "sent",
    cause: "user",
    actor: P.maria,
    origin: "notification",
    project: PR.bertie,
    ref: { kind: "signing_route", id: SIGN_ROUTE },
    link: "page",
    link_path: SIGN_PATH,
    values: { project: PR.bertie.name, profile: TOPIC },
  },
  {
    ago: 2 * DAY + 5 * HOUR,
    template: "project_invitation_link",
    to: "external.reviewer@example.com",
    subject: "Мария Келлер приглашает вас в «Industry adoption of CI»",
    status: "failed",
    reason: "sender_refused",
    smtp_code: 553,
    error:
      "5.7.1 <studio@example.org>: Sender address rejected: not owned by user [скрыто]",
    cause: "user",
    actor: P.maria,
    origin: "project_invite_resend",
    project: PR.ci,
    ref: { kind: "project_invitation", id: "pi_01hy7d3e4f" },
    link: "token",
    values: { actor: P.maria.name, project: PR.ci.name, role: "reader" },
  },
  {
    ago: 2 * DAY + 8 * HOUR,
    template: "access_request",
    to: P.petr,
    subject: "Анна Волкова просит доступ к «Анализ нагрузки на очередь задач»",
    status: "failed",
    reason: "data_refused",
    smtp_code: 552,
    error: "5.3.4 Message size exceeds fixed limit",
    cause: "user",
    actor: P.volkova,
    origin: "notification",
    project: PR.queue,
    ref: { kind: "access_request", id: "ar_01hy7g5h6j" },
    link: "page",
    link_path: "/inbox",
    values: { actor: P.volkova.name, project: PR.queue.name },
  },
  {
    ago: 3 * DAY,
    template: "smtp_test",
    to: P.admin,
    subject: "HSE Doc Studio: проверка почты",
    status: "failed",
    reason: "auth",
    smtp_code: 535,
    error: "5.7.8 Username and Password not accepted for [скрыто]",
    cause: "user",
    actor: P.admin,
    origin: "smtp_test",
    values: { server: MAIL_SERVER },
  },
  {
    ago: 3 * DAY + 2 * HOUR,
    template: "weekly_digest",
    lang: "en",
    to: P.maria,
    subject: "Weekly digest: 3 projects changed",
    status: "sent",
    cause: "system",
    task: "notifications_digest",
    origin: "notification",
  },
  {
    ago: 3 * DAY + 5 * HOUR,
    template: "signing_reminder",
    to: P.elena,
    subject: "Напоминание: Отчёт по практике",
    status: "failed",
    reason: "disconnected",
    error: "Server disconnected unexpectedly",
    cause: "system",
    task: "signing_reminders",
    origin: "signing_auto_reminder",
    project: PR.gone,
    ref: { kind: "signing_route", id: "sr_01hy0z9y8x" },
    link: "page",
    link_path: `/sign/${PR.gone.id}/sr_01hy0z9y8x`,
    values: { project: "Черновик отчёта", profile: "Отчёт по практике" },
  },
  {
    ago: 4 * DAY,
    template: "project_invitation_link",
    to: "n.supervisor@example.org",
    subject: "Мария Келлер приглашает вас в «Bertie: курсовой проект»",
    status: "sent",
    cause: "user",
    actor: P.maria,
    origin: "signing_reinvite",
    project: PR.bertie,
    ref: { kind: "project_invitation", id: "pi_01hy8a2b3c" },
    link: "token",
    values: {
      actor: P.maria.name,
      project: PR.bertie.name,
      role: "reviewer",
    },
  },
  {
    ago: 5 * DAY,
    template: "verify_email",
    to: P.volkova,
    subject: "Подтвердите e-mail",
    status: "sent",
    cause: "anonymous",
    origin: "register",
    link: "token",
  },
  {
    ago: 5 * DAY + 6 * HOUR,
    template: "reset_password",
    to: P.elena,
    subject: "Сброс пароля",
    status: "failed",
    reason: "tls",
    error: "[SSL: WRONG_VERSION_NUMBER] wrong version number (_ssl.c:1006)",
    cause: "anonymous",
    origin: "forgot_password",
    link: "token",
  },
  {
    ago: 6 * DAY,
    template: "invite",
    to: "new.student@example.org",
    subject: "Приглашение в Студию",
    status: "failed",
    reason: "connect",
    error: "Connection refused: smtp.example.org:587",
    duration_ms: 3020,
    cause: "user",
    actor: P.admin,
    origin: "admin_invite_resend",
    ref: { kind: "registration_invite", id: "inv_01hy6d9e0f" },
    link: "token",
    values: { inviter: P.admin.name },
  },
  {
    ago: 6 * DAY + 2 * HOUR,
    template: "transfer_request",
    to: P.dmitry,
    subject: "Пётр Орлов передаёт вам проект «Практика 2025: отчёт»",
    status: "failed",
    reason: "other",
    error: "SMTPResponseException: unexpected reply",
    cause: "user",
    actor: P.petr,
    origin: "notification",
    project: PR.practice,
    ref: { kind: "transfer", id: "tr_01hy8d4e5f" },
    link: "page",
    link_path: "/inbox",
    values: { actor: P.petr.name, project: PR.practice.name },
  },
  {
    ago: 7 * DAY,
    template: "invite",
    to: "first.student@example.org",
    subject: "Приглашение в Студию",
    status: "not_sent",
    reason: "smtp_off",
    cause: "user",
    actor: P.admin,
    origin: "admin_invite",
    ref: { kind: "registration_invite", id: "inv_01hy1a2b3c" },
    link: "token",
    values: { inviter: P.admin.name },
  },
];

/**
 * Почта не настроена: за сутки письма не уходили (`not_sent`, причина «почта не настроена»), а
 * неделю назад, пока SMTP был, уходили.
 */
export const MAIL_SMTP_OFF_DRAFTS: readonly MailDraft[] = [
  {
    ago: 6 * MIN,
    template: "invite",
    to: "new.student@example.org",
    subject: "Приглашение в Студию",
    status: "not_sent",
    reason: "smtp_off",
    cause: "user",
    actor: P.admin,
    origin: "admin_invite",
    ref: { kind: "registration_invite", id: "inv_01hy9a1b2c" },
    link: "token",
    values: { inviter: P.admin.name },
  },
  {
    ago: 35 * MIN,
    template: "signing_request",
    to: P.anna,
    subject: `Мария Келлер просит подписать: ${TOPIC}`,
    status: "not_sent",
    reason: "smtp_off",
    cause: "user",
    actor: P.maria,
    origin: "notification",
    project: PR.bertie,
    ref: { kind: "signing_route", id: SIGN_ROUTE },
    link: "page",
    link_path: SIGN_PATH,
    values: { actor: P.maria.name, project: PR.bertie.name, profile: TOPIC },
  },
  {
    ago: 2 * HOUR,
    template: "verify_email",
    to: P.oleg,
    subject: "Подтвердите e-mail",
    status: "not_sent",
    reason: "smtp_off",
    cause: "anonymous",
    origin: "register",
    link: "token",
  },
  {
    ago: 5 * HOUR,
    template: "reset_notice",
    to: P.dmitry,
    subject: "Администратор выдал ссылку для сброса пароля",
    status: "not_sent",
    reason: "smtp_off",
    cause: "user",
    actor: P.admin,
    origin: "admin_reset_link",
  },
  {
    ago: 11 * HOUR,
    template: "project_invitation",
    to: P.darya,
    subject: "Пётр Орлов приглашает вас в «Практика 2025: отчёт»",
    status: "suppressed",
    reason: "account_blocked",
    cause: "user",
    actor: P.petr,
    origin: "notification",
    project: PR.practice,
    link: "page",
    link_path: "/inbox",
    values: { actor: P.petr.name, project: PR.practice.name, role: "reader" },
  },
  {
    ago: 18 * HOUR,
    template: "signing_reminder",
    to: P.olga,
    subject: "Напоминание: Отчёт по практике",
    status: "not_sent",
    reason: "smtp_off",
    cause: "system",
    task: "signing_reminders",
    origin: "signing_auto_reminder",
    project: PR.queue,
    ref: { kind: "signing_route", id: QUEUE_ROUTE },
    link: "page",
    link_path: QUEUE_PATH,
    values: { project: PR.queue.name, profile: "Отчёт по практике" },
  },
  {
    ago: 8 * DAY,
    template: "smtp_test",
    to: P.admin,
    subject: "HSE Doc Studio: проверка почты",
    status: "sent",
    cause: "user",
    actor: P.admin,
    origin: "smtp_test",
    values: { server: MAIL_SERVER },
  },
  {
    ago: 9 * DAY,
    template: "reset_password",
    to: P.petr,
    subject: "Сброс пароля",
    status: "sent",
    cause: "anonymous",
    origin: "forgot_password",
    link: "token",
  },
];

/**
 * SMTP-сервер отклоняет вход: три часа назад сменили пароль почтового ящика, с тех пор каждое
 * письмо `failed` класса `auth`, до того письма уходили.
 */
export const MAIL_AUTH_FAILURE_DRAFTS: readonly MailDraft[] = [
  ...(
    [
      [3 * MIN, "smtp_test", P.admin, "HSE Doc Studio: проверка почты"],
      [
        20 * MIN,
        "signing_request",
        P.anna,
        `Мария Келлер просит подписать: ${TOPIC}`,
      ],
      [50 * MIN, "reset_password", P.petr, "Сброс пароля"],
      [
        2 * HOUR,
        "project_invitation",
        P.olga,
        "Пётр Орлов приглашает вас в «Практика 2025: отчёт»",
      ],
      [
        3 * HOUR,
        "access_request",
        P.maria,
        "Анна Петрова просит доступ к «Industry adoption of CI»",
      ],
    ] as const
  ).map(([ago, template, to, subject]): MailDraft => ({
    ago,
    template,
    to,
    subject,
    status: "failed",
    reason: "auth",
    smtp_code: 535,
    error: "5.7.8 Authentication credentials invalid",
    cause: template === "reset_password" ? "anonymous" : "user",
    ...(template === "reset_password"
      ? {}
      : { actor: template === "smtp_test" ? P.admin : P.maria }),
    origin:
      template === "smtp_test"
        ? "smtp_test"
        : template === "reset_password"
          ? "forgot_password"
          : "notification",
    link:
      template === "reset_password"
        ? "token"
        : template === "smtp_test"
          ? "none"
          : "page",
    link_path: template === "signing_request" ? SIGN_PATH : "/inbox",
  })),
  ...MAIL_DEFAULT_DRAFTS.filter((d) => d.ago > 4 * HOUR),
];

/** Длинные адреса и темы: таблица и карточка не должны разъезжаться. */
export const MAIL_LONG_DRAFTS: readonly MailDraft[] = [
  {
    ago: 2 * MIN,
    template: "signing_request_new_version",
    to: "konstantin.konstantinopolsky.supervisor.department.of.software.engineering@very-long-university-domain.example.edu",
    subject:
      "Константин Константинопольский просит подписать новую версию: Заявление на утверждение темы выпускной квалификационной работы и назначение научного руководителя",
    status: "sent",
    cause: "user",
    actor: {
      id: "u_01hx7klong1",
      name: "Константин Константинопольский-Преображенский",
      email: "k.konstantinopolsky@example.org",
    },
    origin: "notification",
    project: {
      id: "p_01hxalong01",
      name: "Разработка распределённой системы планирования вычислительных задач с учётом энергопотребления",
    },
    ref: { kind: "signing_route", id: "sr_01hylong01" },
    link: "page",
    link_path: "/sign/p_01hxalong01/sr_01hylong01",
  },
  {
    ago: 9 * MIN,
    template: "project_invitation_link",
    to: "a.very.long.external.address.for.an.invited.reviewer+studio-invitations@subdomain.partner-organization.example.com",
    subject:
      "Константин Константинопольский-Преображенский приглашает вас в «Разработка распределённой системы планирования вычислительных задач с учётом энергопотребления»",
    status: "failed",
    reason: "recipient_refused",
    smtp_code: 550,
    error:
      "5.1.1 <a.very.long.external.address.for.an.invited.reviewer+studio-invitations@subdomain.partner-organization.example.com>: Recipient address rejected: User unknown in virtual mailbox table; please check the address and try again later",
    cause: "user",
    actor: {
      id: "u_01hx7klong1",
      name: "Константин Константинопольский-Преображенский",
      email: "k.konstantinopolsky@example.org",
    },
    origin: "project_invite",
    project: {
      id: "p_01hxalong01",
      name: "Разработка распределённой системы планирования вычислительных задач с учётом энергопотребления",
    },
    link: "token",
  },
];

/** Сколько строк в большом журнале (сценарий admin_scale): листание по курсору. */
export const MAIL_BUSY_COUNT = 1200;

const BUSY_CYCLE: readonly MailDraft[] = MAIL_DEFAULT_DRAFTS.filter(
  (d) => d.template !== "weekly_digest",
);

/**
 * Большой журнал за срок хранения: черновики обычной установки по кругу, по письму каждые
 * полтора часа. Строится детерминированно, без случайностей.
 */
export const makeBusyMailDrafts = (count = MAIL_BUSY_COUNT): MailDraft[] =>
  Array.from({ length: count }, (_, i) => {
    const base = BUSY_CYCLE[i % BUSY_CYCLE.length] ?? MAIL_DEFAULT_DRAFTS[0];
    if (!base) throw new Error("mail log fixtures: empty cycle");
    return { ...base, ago: 3 * MIN + i * 90 * MIN };
  });

/** Журналы демо-мира: обычный, без SMTP, сбой входа на SMTP, пустой, большой. */
export const MAIL_JOURNAL_PROFILES = [
  "default",
  "smtp_off",
  "auth_failure",
  "empty",
  "busy",
] as const;
export type MailJournalProfile = (typeof MAIL_JOURNAL_PROFILES)[number];

export const mailDraftsOf = (profile: MailJournalProfile): MailDraft[] => {
  switch (profile) {
    case "default":
      return [...MAIL_DEFAULT_DRAFTS];
    case "smtp_off":
      return [...MAIL_SMTP_OFF_DRAFTS];
    case "auth_failure":
      return [...MAIL_AUTH_FAILURE_DRAFTS];
    case "empty":
      return [];
    case "busy":
      return makeBusyMailDrafts();
  }
};

/** Почта настроена в этом журнале (плашка «Почта не настроена» только у smtp_off). */
export const mailSmtpConfiguredOf = (profile: MailJournalProfile): boolean =>
  profile !== "smtp_off";

// ── Состояния галереи (4.4) ───────────────────────────────────────────────

export const MAIL_JOURNALS: Record<MailJournalProfile, MailLogRecord[]> = {
  default: makeMailJournal(MAIL_DEFAULT_DRAFTS),
  smtp_off: makeMailJournal(MAIL_SMTP_OFF_DRAFTS),
  auth_failure: makeMailJournal(MAIL_AUTH_FAILURE_DRAFTS),
  empty: [],
  busy: makeMailJournal(makeBusyMailDrafts()),
};

const DEFAULT_JOURNAL = MAIL_JOURNALS.default;
const LONG_JOURNAL = makeMailJournal(MAIL_LONG_DRAFTS, NOW_MS, 9001);

const findRecord = (
  journal: readonly MailLogRecord[],
  match: (entry: MailLogEntry) => boolean,
): MailLogRecord => {
  const found = journal.find((r) => match(r.entry));
  if (!found) throw new Error("mail log fixtures: no such record");
  return found;
};

/**
 * Страницы списка. Эталоны сервера (contracts/server/fixtures/AdminMailLogPage): `day` (есть
 * `next_cursor`, подгрузка следующей), `next_page`, `filtered_failed` (с фильтром, без оценки числа),
 * `empty` (писем не было). Свои: `mixed` (все виды и итоги демо-мира), `nothing_found`, `smtp_off`,
 * `auth_failure`, `long` (длинные адреса и темы).
 */
export const MAIL_LOG_PAGES = {
  ...MAIL_LOG_SERVER_PAGES,
  mixed: makeMailLogPage(DEFAULT_JOURNAL),
  nothing_found: makeMailLogPage([], { totalEstimate: null }),
  smtp_off: makeMailLogPage(MAIL_JOURNALS.smtp_off),
  auth_failure: makeMailLogPage(MAIL_JOURNALS.auth_failure),
  long: makeMailLogPage([...LONG_JOURNAL, ...DEFAULT_JOURNAL.slice(0, 3)]),
  // Фильтр «Ждут повтора» из полосы за сутки (14.3).
  retrying: makeMailLogPage(
    DEFAULT_JOURNAL.filter(
      (r) => r.entry.status === "failed" && r.entry.next_attempt_at !== null,
    ),
    { totalEstimate: null },
  ),
} satisfies Record<string, MailLogPage>;
export type MailLogPageState = keyof typeof MAIL_LOG_PAGES;

/**
 * Полоса за сутки и плашка: эталоны сервера (AdminMailLogSummary) `normal`, `auth_failure`,
 * `smtp_off`, `quiet`.
 */
export const MAIL_LOG_SUMMARIES = {
  ...MAIL_LOG_SERVER_SUMMARIES,
} satisfies Record<string, MailLogSummary>;
export type MailLogSummaryState = keyof typeof MAIL_LOG_SUMMARIES;

/** Строки демо-журнала с особыми случаями: на них проверяется превью и стоят свои карточки галереи. */
export const MAIL_LOG_RECORDS = {
  /** Сброс пароля ушёл: ссылка с токеном скрыта, вызвал запрос без входа. */
  token_link: findRecord(
    DEFAULT_JOURNAL,
    (e) => e.template === "reset_password" && e.status === "sent",
  ),
  /** Просьба подписать: адрес страницы маршрута текстом. */
  signing_page: findRecord(
    DEFAULT_JOURNAL,
    (e) => e.template === "signing_request" && e.status === "sent",
  ),
  /** Приглашение в проект по ссылке с сообщением приглашающего. */
  invitation_note: findRecord(
    DEFAULT_JOURNAL,
    (e) =>
      e.template === "project_invitation_link" &&
      e.status === "sent" &&
      e.origin === "project_invite",
  ),
  /** Шаблон менялся после отправки: тема перерисовки другая. */
  rerendered: findRecord(
    DEFAULT_JOURNAL,
    (e) => e.template === "invite" && e.status === "sent",
  ),
  /** Вида письма в этой версии нет: превью нет. */
  template_gone: findRecord(DEFAULT_JOURNAL, (e) => !e.template_known),
  /** Адрес отвергнут: 550. */
  failed_550: findRecord(DEFAULT_JOURNAL, (e) => e.failure?.smtp_code === 550),
  /** SMTP-сервер не принял логин: ссылка на настройки почты. */
  failed_auth: findRecord(DEFAULT_JOURNAL, (e) => e.reason === "auth"),
  /** Письмо не положено: почта не подтверждена. */
  suppressed_unverified: findRecord(
    DEFAULT_JOURNAL,
    (e) => e.reason === "email_unverified",
  ),
  /** Письмо не положено: вход закрыт. */
  suppressed_blocked: findRecord(
    DEFAULT_JOURNAL,
    (e) => e.reason === "account_blocked",
  ),
  /** Почта не настроена. */
  not_sent: findRecord(
    MAIL_JOURNALS.smtp_off,
    (e) => e.template === "invite" && e.status === "not_sent",
  ),
  /** Регистрация: запрос без входа. */
  anonymous: findRecord(
    DEFAULT_JOURNAL,
    (e) => e.cause === "anonymous" && e.origin === "register",
  ),
  /** Автонапоминание маршрута: фоновая задача. */
  system_task: findRecord(
    DEFAULT_JOURNAL,
    (e) => e.cause === "system" && e.status === "sent" && e.template_known,
  ),
  /** Проект удалён: название не известно, ссылки на него нет. */
  project_gone: findRecord(DEFAULT_JOURNAL, (e) => e.project?.name === null),
  /** Длинные адрес, тема, имя и проект. */
  long: findRecord(LONG_JOURNAL, (e) => e.status === "failed"),
  /** Временный сбой: ждёт автоповтора (14, V6). */
  retrying: findRecord(DEFAULT_JOURNAL, (e) => e.next_attempt_at !== null),
  /** Пять попыток не помогли: можно «Отправить ещё раз». */
  gave_up: findRecord(
    DEFAULT_JOURNAL,
    (e) => e.template === "checkpoint_due" && e.attempts > 1,
  ),
} satisfies Record<string, MailLogRecord>;

const GAVE_UP = MAIL_LOG_RECORDS.gave_up;
/** Ручной повтор строки GAVE_UP, который дошёл (14, V2). */
const RESENT_COPY = makeMailLogRecord(
  {
    ago: 60,
    template: "checkpoint_due",
    to: P.anna,
    subject: GAVE_UP.entry.subject,
    status: "sent",
    cause: "user",
    actor: P.maria,
    origin: "admin_resend",
    project: PR.bertie,
    link: "page",
    link_path: GAVE_UP.link_path ?? "/",
    values: { ...GAVE_UP.values },
    resent_from_id: GAVE_UP.entry.id,
  },
  GAVE_UP.entry.id + 5000,
);
export type MailLogRecordState = keyof typeof MAIL_LOG_RECORDS;

/**
 * Карточки галереи (4.2, 4.4). Эталоны сервера (AdminMailLogDetail): `token_link`, `page_link`,
 * `failed_with_note` (550 и сообщение), `failed_auth_system` (фоновая задача, EN), `suppressed`
 * (почта не подтверждена), `not_sent`, `rerendered`, `template_gone`. Свои, которых в эталонах нет:
 * `suppressed_blocked`, `project_gone` (проекта и вызвавшего уже нет), `long`. Запись, удалённую по
 * сроку, показывает 404 (MAIL_LOG_MISSING_ID), а не карточка.
 */
export const MAIL_LOG_DETAILS = {
  ...MAIL_LOG_SERVER_DETAILS,
  suppressed_blocked: makeMailLogDetail(MAIL_LOG_RECORDS.suppressed_blocked),
  // Строка демо-журнала с удалённым проектом пришла от фоновой задачи; здесь её вызвал человек,
  // которого уже стёрли: в «Вызвал» стоит «Пользователь удалён».
  project_gone: makeMailLogDetail({
    ...MAIL_LOG_RECORDS.project_gone,
    entry: {
      ...MAIL_LOG_RECORDS.project_gone.entry,
      cause: "user",
      actor: null,
      task: null,
      origin: "notification",
    },
  }),
  long: makeMailLogDetail(MAIL_LOG_RECORDS.long),
  // Версия 2 (раздел 14): ждёт автоповтора, можно отправить ещё раз, уже неактуально, повторено.
  retrying: makeMailLogDetail(MAIL_LOG_RECORDS.retrying),
  resend_allowed: makeMailLogDetail(GAVE_UP),
  stale_route: makeMailLogDetail({
    ...MAIL_LOG_RECORDS.retrying,
    entry: {
      ...MAIL_LOG_RECORDS.retrying.entry,
      attempts: 5,
      next_attempt_at: null,
    },
    stale: "route_done",
  }),
  resent: makeMailLogDetail(GAVE_UP, { journal: [RESENT_COPY, GAVE_UP] }),
  resent_copy: makeMailLogDetail(RESENT_COPY),
} satisfies Record<string, MailLogDetail>;
export type MailLogDetailState = keyof typeof MAIL_LOG_DETAILS;

/** Id строки, которой нет (удалена по сроку): карточка показывает «Письмо не найдено». */
export const MAIL_LOG_MISSING_ID = 404404;
