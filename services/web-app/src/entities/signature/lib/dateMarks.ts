import type { DateMarkFormat } from "../api/signatureSchemas";

// Текст метки даты (docs/design/signing-route.md, 14.3), как его печатает сервер
// (`core/signatures/dates.py`): момент переводится в пояс отображения, язык месяца по языку
// документа. Пояс один, Москва, без tzdata постоянное UTC+3 (14.4). Фронту это нужно для примера
// по сегодняшней дате в редакторе, для оценки «текст не помещается в рамку» и для демо.

export const DATE_MARK_FORMATS: readonly DateMarkFormat[] = [
  "day",
  "month_word",
  "month_number",
  "year",
  "year_short",
  "date_numeric",
  "date_long",
];

const DISPLAY_OFFSET_MS = 3 * 60 * 60 * 1000;

// Родительный падеж: «13 ноября».
const MONTHS_RU = [
  "января",
  "февраля",
  "марта",
  "апреля",
  "мая",
  "июня",
  "июля",
  "августа",
  "сентября",
  "октября",
  "ноября",
  "декабря",
];

const MONTHS_EN = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
];

type Day = { year: number; month: number; day: number };

const DAY_ONLY = /^(\d{4})-(\d{2})-(\d{2})$/;

/** День по Москве: у ручной даты («2026-11-13») он и есть; у момента с временем переводится в пояс. */
const dayOf = (moment: string): Day | null => {
  const only = DAY_ONLY.exec(moment);
  if (only) {
    return {
      year: Number(only[1]),
      month: Number(only[2]),
      day: Number(only[3]),
    };
  }
  const ms = Date.parse(moment);
  if (Number.isNaN(ms)) return null;
  const shifted = new Date(ms + DISPLAY_OFFSET_MS);
  return {
    year: shifted.getUTCFullYear(),
    month: shifted.getUTCMonth() + 1,
    day: shifted.getUTCDate(),
  };
};

const pad2 = (n: number): string => String(n).padStart(2, "0");

const formatDay = (d: Day, format: DateMarkFormat, lang: string): string => {
  const ru = !lang.startsWith("en");
  const month = (ru ? MONTHS_RU : MONTHS_EN)[d.month - 1] ?? "";
  switch (format) {
    case "day":
      return String(d.day);
    case "month_word":
      return month;
    case "month_number":
      return pad2(d.month);
    case "year":
      return String(d.year);
    case "year_short":
      return pad2(d.year % 100);
    case "date_numeric":
      return `${pad2(d.day)}.${pad2(d.month)}.${String(d.year)}`;
    case "date_long":
      return ru
        ? `${String(d.day)} ${month} ${String(d.year)} г.`
        : `${String(d.day)} ${month} ${String(d.year)}`;
  }
};

/** Текст метки по моменту подписи; пустая строка, если момент не разобрать. */
export const formatDateMark = (
  moment: string,
  format: DateMarkFormat,
  lang: string,
): string => {
  const d = dayOf(moment);
  return d === null ? "" : formatDay(d, format, lang);
};

/** Сегодняшний день по Москве, «2026-11-13». */
export const todayInDisplayZone = (now: number = Date.now()): string => {
  const shifted = new Date(now + DISPLAY_OFFSET_MS);
  return `${String(shifted.getUTCFullYear())}-${pad2(shifted.getUTCMonth() + 1)}-${pad2(shifted.getUTCDate())}`;
};

/** Самый длинный текст формата за год: по нему видно, поместится ли любая дата. */
export const longestDateText = (
  format: DateMarkFormat,
  lang: string,
  year = 2026,
): string =>
  Array.from({ length: 12 }, (_, i) =>
    formatDay({ year, month: i + 1, day: 28 }, format, lang),
  ).reduce((a, b) => (b.length > a.length ? b : a), "");

const PT_PER_MM = 72 / 25.4;
/** Наименьший кегль метки на сервере (14.13). */
const MIN_FONT_PT = 6;
/** Средняя ширина знака шрифта плашки в долях кегля (с запасом). */
const CHAR_EM = 0.55;
/** Высота строки в долях кегля: кегль по высоте рамки. */
const LINE_EM = 1.2;

/** Кегль метки, как его подберёт сервер: по высоте рамки, затем меньше, пока текст не влезет. */
export const dateMarkFontPt = (
  text: string,
  widthMm: number,
  heightMm: number,
): number => {
  const byHeight = (heightMm * PT_PER_MM) / LINE_EM;
  const byWidth =
    text.length > 0
      ? (widthMm * PT_PER_MM) / (text.length * CHAR_EM)
      : byHeight;
  return Math.min(byHeight, byWidth);
};

/** Поместится ли текст в рамку не меньше чем шестым кеглем. */
export const dateMarkFits = (
  text: string,
  widthMm: number,
  heightMm: number,
): boolean => dateMarkFontPt(text, widthMm, heightMm) >= MIN_FONT_PT;
