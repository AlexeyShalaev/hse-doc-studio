// Срок контрольной точки по Москве (docs/design/signing-route.md, 16.3 и 16.6): ввод и показ в
// поясе отображения (`DISPLAY_ZONE`, 14.4), постоянное UTC+3 без перехода на летнее время. Дни
// считаются по календарю Москвы: срок 15.11 в 10:00 вечером 14.11 это «через 1 день».

const OFFSET_MS = 3 * 60 * 60 * 1000;
const DAY_MS = 24 * 60 * 60 * 1000;
/** Пояс в ISO, который пишет сервер (`+03:00`). */
export const DISPLAY_OFFSET = "+03:00";
/** Время срока по умолчанию (16.2): конец дня. */
export const DEFAULT_DEADLINE_TIME = "23:59";

const pad2 = (n: number): string => String(n).padStart(2, "0");

/** Части момента по Москве; null, если ISO не разобрать. */
export type MoscowParts = {
  year: number;
  month: number;
  day: number;
  hour: number;
  minute: number;
};

export const moscowParts = (iso: string): MoscowParts | null => {
  const ms = Date.parse(iso);
  if (Number.isNaN(ms)) return null;
  const at = new Date(ms + OFFSET_MS);
  return {
    year: at.getUTCFullYear(),
    month: at.getUTCMonth() + 1,
    day: at.getUTCDate(),
    hour: at.getUTCHours(),
    minute: at.getUTCMinutes(),
  };
};

/** Номер календарного дня по Москве: разница номеров это разница дат. */
const moscowDay = (ms: number): number => Math.floor((ms + OFFSET_MS) / DAY_MS);

/**
 * Сколько календарных дней по Москве до срока: 0 сегодня, 1 завтра, меньше нуля, если день срока
 * прошёл. Той же разницей дат сервер отличает `today` от `soon` (16.6).
 */
export const daysUntilDeadline = (iso: string, now: number): number | null => {
  const ms = Date.parse(iso);
  return Number.isNaN(ms) ? null : moscowDay(ms) - moscowDay(now);
};

/** Момент в ISO с поясом Москвы, как его отдаёт сервер: «2026-11-15T23:59:00+03:00». */
export const toMoscowIso = (ms: number): string => {
  const at = new Date(ms + OFFSET_MS);
  return `${String(at.getUTCFullYear())}-${pad2(at.getUTCMonth() + 1)}-${pad2(at.getUTCDate())}T${pad2(at.getUTCHours())}:${pad2(at.getUTCMinutes())}:00${DISPLAY_OFFSET}`;
};

const DATE_RE = /^(\d{4})-(\d{2})-(\d{2})$/;
const TIME_RE = /^(\d{2}):(\d{2})$/;

/**
 * Поля формы (дата «2026-11-15» и время «23:59» по Москве) в срок для `PUT .../deadline`; null,
 * если дата или время не разбираются. Пустое время значит конец дня.
 */
export const deadlineFromInput = (
  date: string,
  time: string,
): string | null => {
  const d = DATE_RE.exec(date);
  const t = TIME_RE.exec(time === "" ? DEFAULT_DEADLINE_TIME : time);
  if (!d || !t) return null;
  const [year, month, day] = [Number(d[1]), Number(d[2]), Number(d[3])];
  const [hour, minute] = [Number(t[1]), Number(t[2])];
  if (hour > 23 || minute > 59) return null;
  const ms = Date.UTC(year, month - 1, day, hour, minute) - OFFSET_MS;
  // 31.02 и подобное Date.UTC молча переносит на следующий месяц: такую дату не принимаем.
  const back = moscowParts(new Date(ms).toISOString());
  if (back?.year !== year || back.month !== month || back.day !== day) {
    return null;
  }
  return toMoscowIso(ms);
};

/** Срок в поля формы по Москве; без срока пустая дата и время по умолчанию. */
export const deadlineToInput = (
  iso: string | null,
): { date: string; time: string } => {
  const parts = iso === null ? null : moscowParts(iso);
  if (parts === null) return { date: "", time: DEFAULT_DEADLINE_TIME };
  return {
    date: `${String(parts.year)}-${pad2(parts.month)}-${pad2(parts.day)}`,
    time: `${pad2(parts.hour)}:${pad2(parts.minute)}`,
  };
};

/** «15.11» (год, если он не текущий по Москве: «15.11.2027»). */
export const formatDeadlineDay = (iso: string, now: number): string => {
  const parts = moscowParts(iso);
  if (parts === null) return "";
  const current = moscowParts(new Date(now).toISOString())?.year;
  const base = `${pad2(parts.day)}.${pad2(parts.month)}`;
  return parts.year === current ? base : `${base}.${String(parts.year)}`;
};

/** «23:59» по Москве. */
export const formatDeadlineTime = (iso: string): string => {
  const parts = moscowParts(iso);
  return parts === null ? "" : `${pad2(parts.hour)}:${pad2(parts.minute)}`;
};

/** Тот же момент, в каком бы поясе его ни записали. */
export const sameMoment = (a: string | null, b: string | null): boolean =>
  a === null || b === null ? a === b : Date.parse(a) === Date.parse(b);

/**
 * Срок маршрута из срока точки (16.5): на сутки раньше в то же время; ближе двух суток до срока
 * точки равен ему; срок точки прошёл или его нет, значит срока маршрута нет. Тем же правилом R29
 * заполняет срок нового черновика на сервере, а редактор предлагает его кнопкой «Поставить».
 */
export const routeDeadlineFromPoint = (
  point: string | null,
  now: number,
): string | null => {
  if (point === null) return null;
  const ms = Date.parse(point);
  if (Number.isNaN(ms) || ms <= now) return null;
  return toMoscowIso(ms - now < 2 * DAY_MS ? ms : ms - DAY_MS);
};
