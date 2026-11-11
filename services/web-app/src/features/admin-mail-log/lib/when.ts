import { useEffect, useState } from "react";

// Время строки журнала писем (docs/design/mail-log.md, 4.1). Сегодняшнее письмо: «14:32»,
// вчерашнее: «вчера, 14:32», старше: «10 нояб., 14:32» (год, если не текущий). Полная дата
// в подсказке.

export type MailWhen = {
  /** Какой это день относительно now. */
  day: "today" | "yesterday" | "earlier";
  /** «14:32». */
  time: string;
  /** «10 нояб.» или «10 нояб. 2025 г.»; у сегодняшнего и вчерашнего не нужна, но есть. */
  date: string;
  /** «11 ноября 2026 г., 14:32:05»: подсказка при наведении. */
  full: string;
};

const startOfDay = (ms: number): number => {
  const d = new Date(ms);
  d.setHours(0, 0, 0, 0);
  return d.getTime();
};

/** Разбор времени строки; null, если сервер прислал не дату. */
export const mailWhen = (
  iso: string,
  now: number,
  locale: string,
): MailWhen | null => {
  const at = new Date(iso);
  const ms = at.getTime();
  if (Number.isNaN(ms)) return null;
  const today = startOfDay(now);
  const yesterday = startOfDay(today - 1);
  const day = ms >= today ? "today" : ms >= yesterday ? "yesterday" : "earlier";
  const sameYear = at.getFullYear() === new Date(now).getFullYear();
  return {
    day,
    time: at.toLocaleTimeString(locale, { hour: "2-digit", minute: "2-digit" }),
    date: at.toLocaleDateString(locale, {
      day: "numeric",
      month: "short",
      ...(sameYear ? {} : { year: "numeric" }),
    }),
    full: at.toLocaleString(locale, { dateStyle: "long", timeStyle: "medium" }),
  };
};

/** Текущее время, раз в минуту новое: «сегодня» и «вчера» в журнале не застревают после полуночи. */
export const useMinuteNow = (): number => {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = window.setInterval(() => {
      setNow(Date.now());
    }, 60_000);
    return () => {
      window.clearInterval(id);
    };
  }, []);
  return now;
};
