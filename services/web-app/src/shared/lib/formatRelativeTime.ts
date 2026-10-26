import { localeTag } from "./i18n";

// "3 минуты назад" / "in 2 hours" in the interface language. Intl does the
// plural forms; numeric:"auto" gives "вчера" / "yesterday" and "сейчас" / "now".

const MINUTE = 60;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;
const MONTH = 30 * DAY;
const YEAR = 365 * DAY;

const UNITS: [
  limit: number,
  unit: Intl.RelativeTimeFormatUnit,
  size: number,
][] = [
  [MINUTE, "second", 1],
  [HOUR, "minute", MINUTE],
  [DAY, "hour", HOUR],
  [MONTH, "day", DAY],
  [YEAR, "month", MONTH],
  [Infinity, "year", YEAR],
];

// Under this many seconds the age is shown as "now": a counter that flips every
// second makes a status line jitter and tells the user nothing.
const NOW_WINDOW_S = 10;

export const formatRelativeTime = (
  value: string | number | Date | null | undefined,
  now: number | Date = Date.now(),
): string => {
  if (value == null || value === "") return "";
  const then = new Date(value).getTime();
  if (Number.isNaN(then)) return "";
  const seconds = Math.round((then - new Date(now).getTime()) / 1000);
  const abs = Math.abs(seconds);
  const rtf = new Intl.RelativeTimeFormat(localeTag(), { numeric: "auto" });
  if (abs < NOW_WINDOW_S) return rtf.format(0, "second");
  for (const [limit, unit, size] of UNITS) {
    if (abs < limit) return rtf.format(Math.round(seconds / size), unit);
  }
  return "";
};
