import { demoError, demoJson } from "@shared/api/demo";
import type { DemoRequest, DemoResponse, DemoRoute } from "@shared/api/demo";
import { MAIL_STATUSES, type MailStatus } from "../api/schemas";
import {
  makeMailJournal,
  makeMailLogDetail,
  makeMailLogRecord,
  makeMailLogSummary,
  mailDraftsOf,
  type MailDraft,
  type MailJournalProfile,
  type MailLogRecord,
} from "./fixtures";

// Моки журнала писем поверх демо-транспорта (docs/design/mail-log.md, раздел 6): те же адреса,
// параметры, коды и формы, что у сервера. Бэкенда (B1..B6) ещё нет: на этих моках ведутся экраны
// W2 и W3. Журнал строится от текущего времени при первом обращении и живёт до reset().

export type MailLogDemoActor = { id: string; name: string; admin: boolean };

export type MailLogDemoOptions = {
  /** null: не вошёл (401); `admin: false`: 404, как у всей админки. */
  getActor: () => MailLogDemoActor | null;
  /** Какой журнал у установки: обычный, без SMTP, сбой входа, пустой, большой. */
  profile: () => MailJournalProfile;
  /** Настроена ли почта сейчас: плашка «Почта не настроена» в сводке. */
  smtpConfigured: () => boolean;
  now?: () => number;
};

export type MailLogDemo = {
  /** Маршруты клиента /api/admin. */
  routes: DemoRoute[];
  /** Дописать попытку отправки «сейчас» (например, тестовое письмо из блока «Почта (SMTP)»). */
  record: (draft: Omit<MailDraft, "ago">) => MailLogRecord;
  /** Строки журнала, новые сверху. */
  journal: () => readonly MailLogRecord[];
  reset: () => void;
};

const DEFAULT_LIMIT = 50;
const MAX_LIMIT = 200;
const SEARCH_MAX = 200;
const EMAIL_MAX = 320;
const ID_MAX = 64;
const TEMPLATE_RE = /^[a-z_]{1,64}$/;
/** Параметры GET /mail-log (6.1); лишний параметр даёт 422, как у сервера. */
const PARAMS = new Set([
  "template",
  "status",
  "reason",
  "recipient_id",
  "recipient",
  "project_id",
  "from",
  "to",
  "q",
  "cursor",
  "limit",
]);

const invalid = (): DemoResponse =>
  demoError(422, "input_invalid", "Invalid query parameters");
const notFound = (): DemoResponse => demoError(404, "not_found", "Not Found");

const all = (req: DemoRequest, key: string): string[] => {
  const value = req.query[key];
  return value === undefined ? [] : Array.isArray(value) ? value : [value];
};
/** Одно значение; пустое значит «не задано». Повторы отсекает parseFilters. */
const one = (req: DemoRequest, key: string): string | null => {
  const value = all(req, key)[0];
  return value === undefined || value === "" ? null : value;
};
/** Параметры, которые повторять нельзя. */
const SINGLE = [
  "reason",
  "recipient_id",
  "recipient",
  "project_id",
  "q",
  "from",
  "to",
  "cursor",
  "limit",
];

// Курсор журнала: base64url от id последней строки, как у остальных журналов демо.
const toB64Url = (text: string): string =>
  btoa(text).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
export const encodeMailCursor = (id: number): string =>
  toB64Url(`k:${String(id)}`);
const decodeCursor = (raw: string): number | null => {
  try {
    const b64 = raw.replace(/-/g, "+").replace(/_/g, "/");
    const text = atob(b64 + "=".repeat((4 - (b64.length % 4)) % 4));
    const match = /^k:(\d+)$/.exec(text);
    return match ? Number(match[1]) : null;
  } catch {
    return null;
  }
};

type Filter = (record: MailLogRecord) => boolean;

/** Условия запроса по И; null при неверном параметре (422). */
const parseFilters = (
  req: DemoRequest,
): { filters: Filter[]; cursor: number | null; limit: number } | null => {
  if (Object.keys(req.query).some((key) => !PARAMS.has(key))) return null;
  const filters: Filter[] = [];

  const templates = all(req, "template");
  if (templates.some((t) => !TEMPLATE_RE.test(t))) return null;
  if (templates.length > 0) {
    filters.push((r) => templates.includes(r.entry.template));
  }
  const statuses = all(req, "status");
  if (statuses.some((s) => !MAIL_STATUSES.includes(s as MailStatus))) {
    return null;
  }
  if (statuses.length > 0) {
    filters.push((r) => statuses.includes(r.entry.status));
  }

  if (SINGLE.some((key) => all(req, key).length > 1)) return null;
  const reason = one(req, "reason");
  const recipientId = one(req, "recipient_id");
  const recipient = one(req, "recipient");
  const projectId = one(req, "project_id");
  const q = one(req, "q");
  const fromRaw = one(req, "from");
  const toRaw = one(req, "to");
  const cursorRaw = one(req, "cursor");
  const limitRaw = one(req, "limit");

  if (reason !== null) {
    filters.push((r) => r.entry.reason === reason);
  }
  if (recipientId !== null) {
    if (recipientId.length > ID_MAX) return null;
    filters.push((r) => r.entry.to_user?.id === recipientId);
  }
  if (recipient !== null) {
    if (recipient.length > EMAIL_MAX || !recipient.includes("@")) return null;
    const wanted = recipient.trim().toLowerCase();
    filters.push((r) => r.entry.to_email.toLowerCase() === wanted);
  }
  if (projectId !== null) {
    filters.push((r) => r.entry.project?.id === projectId);
  }
  if (q !== null) {
    if (q.length > SEARCH_MAX) return null;
    const needle = q.trim().toLowerCase();
    if (needle !== "") {
      filters.push(
        (r) =>
          r.entry.to_email.toLowerCase().includes(needle) ||
          r.entry.subject.toLowerCase().includes(needle),
      );
    }
  }
  const from = fromRaw === null ? null : Date.parse(fromRaw);
  const to = toRaw === null ? null : Date.parse(toRaw);
  if (Number.isNaN(from) || Number.isNaN(to)) return null;
  if (from !== null && to !== null && from > to) return null;
  if (from !== null) filters.push((r) => Date.parse(r.entry.at) >= from);
  if (to !== null) filters.push((r) => Date.parse(r.entry.at) < to);

  let cursor: number | null = null;
  if (cursorRaw !== null) {
    cursor = decodeCursor(cursorRaw);
    if (cursor === null) return null;
  }
  let limit = DEFAULT_LIMIT;
  if (limitRaw !== null) {
    limit = Number(limitRaw);
    if (!Number.isInteger(limit) || limit < 1 || limit > MAX_LIMIT) {
      return null;
    }
  }
  return { filters, cursor, limit };
};

export const createMailLogDemo = (options: MailLogDemoOptions): MailLogDemo => {
  const now = options.now ?? Date.now;
  let journal: MailLogRecord[] | null = null;

  const rows = (): MailLogRecord[] => {
    journal ??= makeMailJournal(mailDraftsOf(options.profile()), now());
    return journal;
  };

  const guard = (): DemoResponse | null => {
    const actor = options.getActor();
    if (!actor) {
      return demoError(401, "auth_required", "Authentication required");
    }
    return actor.admin ? null : notFound();
  };

  const page = (req: DemoRequest): DemoResponse => {
    const parsed = parseFilters(req);
    if (!parsed) return invalid();
    const { filters, cursor, limit } = parsed;
    const items: MailLogRecord[] = [];
    let more = false;
    for (const record of rows()) {
      if (cursor !== null && record.entry.id >= cursor) continue;
      if (!filters.every((accept) => accept(record))) continue;
      if (items.length === limit) {
        more = true;
        break;
      }
      items.push(record);
    }
    const last = items[items.length - 1];
    return demoJson({
      items: items.map((r) => structuredClone(r.entry)),
      next_cursor: more && last ? encodeMailCursor(last.entry.id) : null,
      // Оценка числа только без фильтров, как у журнала аудита.
      total_estimate: filters.length === 0 ? rows().length : null,
    });
  };

  const routes: DemoRoute[] = [
    {
      method: "GET",
      pattern: "/mail-log",
      handler: (req) => guard() ?? page(req),
    },
    // Раньше карточки: «summary» не должен уйти в /mail-log/:id.
    {
      method: "GET",
      pattern: "/mail-log/summary",
      handler: () =>
        guard() ??
        demoJson(
          makeMailLogSummary(rows(), {
            smtpConfigured: options.smtpConfigured(),
            nowMs: now(),
          }),
        ),
    },
    {
      method: "GET",
      pattern: "/mail-log/:id",
      handler: (req) => {
        const refused = guard();
        if (refused) return refused;
        const raw = req.params.id ?? "";
        if (!/^\d{1,15}$/.test(raw)) return invalid();
        const id = Number(raw);
        const record = rows().find((r) => r.entry.id === id);
        return record ? demoJson(makeMailLogDetail(record)) : notFound();
      },
    },
  ];

  return {
    routes,
    record: (draft) => {
      const current = rows();
      const id = (current[0]?.entry.id ?? 0) + 1;
      const record = makeMailLogRecord({ ...draft, ago: 0 }, id, now());
      current.unshift(record);
      return record;
    },
    journal: () => rows(),
    reset: () => {
      journal = null;
    },
  };
};
