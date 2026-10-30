import type { AdminAuditEvent, AdminUser } from "@entities/session";

// Журнал аудита для людей: раздел действия, понятная цель и дни. Сырые коды и
// идентификаторы на экран не выходят, они остаются в раскрытых подробностях.

export type AuditCategory =
  | "auth"
  | "admin"
  | "invite"
  | "org"
  | "group"
  | "settings"
  | "runner"
  | "project"
  | "other";

const CATEGORY_OF: Record<string, AuditCategory> = {
  auth: "auth",
  account: "auth",
  pat: "auth",
  admin: "admin",
  invite: "invite",
  org: "org",
  group: "group",
  settings: "settings",
  setup: "settings",
  signing: "settings",
  oidc: "settings",
  runner: "runner",
  project: "project",
};

export const auditCategory = (action: string): AuditCategory =>
  CATEGORY_OF[action.split(".")[0] ?? ""] ?? "other";

export type AuditTone = "neutral" | "warning" | "danger";

/** Отказы и сбои выделены красным, удаление и отзыв жёлтым, остальное спокойно. */
export const auditTone = (action: string): AuditTone => {
  if (/(failed|denied|rejected)$/.test(action)) return "danger";
  if (/(delete|deleted|revoke|revoked|disabled|remove|leave)$/.test(action)) {
    return "warning";
  }
  return "neutral";
};

// Служебные идентификаторы (u_01hx…, uuid) людям ни о чём не говорят.
export const looksLikeId = (value: string): boolean =>
  /^[a-z]{1,6}_(?=[0-9a-z]*\d)[0-9a-z]{2,}$/i.test(value) ||
  /^[0-9a-f]{8}-[0-9a-f]{4}-/i.test(value) ||
  /^[0-9a-f]{24,}$/i.test(value);

// Поля details, которые сами по себе читаются как название цели.
const NAME_KEYS = ["name", "label", "email", "slug", "title"] as const;

export type AuditTarget =
  | { kind: "person"; user: AdminUser }
  | { kind: "text"; text: string; key: string | null };

/** На что направлено действие: человек по id, иначе понятное поле из details. */
export const auditTarget = (
  event: AdminAuditEvent,
  people: ReadonlyMap<string, AdminUser>,
): AuditTarget | null => {
  const person = event.target ? people.get(event.target) : undefined;
  if (person) return { kind: "person", user: person };
  for (const key of NAME_KEYS) {
    const value = event.details[key];
    if (typeof value === "string" && value.trim() !== "") {
      return { kind: "text", text: value, key };
    }
  }
  if (event.target && !looksLikeId(event.target)) {
    return { kind: "text", text: event.target, key: null };
  }
  return null;
};

/** Ключ дня в местном времени: события группируются по нему. */
export const dayKey = (iso: string): string => {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "unknown";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${String(date.getFullYear())}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
};

export type AuditDay = { key: string; events: AdminAuditEvent[] };

/** События подряд по дням; порядок внутри дня сохраняется (новые сверху). */
export const groupByDay = (events: readonly AdminAuditEvent[]): AuditDay[] => {
  const days: AuditDay[] = [];
  for (const event of events) {
    const key = dayKey(event.at);
    const last = days[days.length - 1];
    if (last?.key === key) last.events.push(event);
    else days.push({ key, events: [event] });
  }
  return days;
};

/** Сколько дней между днём события и сегодняшним (0 сегодня, 1 вчера). */
export const daysAgo = (key: string, now: Date): number => {
  const [y, m, d] = key.split("-").map(Number);
  if (y === undefined || m === undefined || d === undefined) return Infinity;
  const day = new Date(y, m - 1, d).getTime();
  const today = new Date(
    now.getFullYear(),
    now.getMonth(),
    now.getDate(),
  ).getTime();
  return Math.round((today - day) / 86_400_000);
};
