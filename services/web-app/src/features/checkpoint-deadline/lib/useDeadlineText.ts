import { useCallback, useMemo } from "react";
import { useTranslation } from "react-i18next";
import type { NextDeadline } from "@entities/session";
import {
  daysUntilDeadline,
  formatDeadlineDay,
  formatDeadlineTime,
  type DeadlineState,
} from "@entities/submission";
import { pickLocalized } from "@shared/lib";

// Тексты срока контрольной точки (docs/design/signing-route.md, 16.2 и 16.6). Состояние даёт
// сервер; «через N дней» фронт считает той же разницей дат по Москве, что и сервер.

/** Срок точки так, как его отдаёт профиль сдачи. */
export type PointDeadline = {
  deadline: string | null;
  deadline_state: DeadlineState;
  packaged_at: string | null;
};

export type DeadlineTone = "neutral" | "warn" | "err" | "ok";

export const DEADLINE_TONE: Record<DeadlineState, DeadlineTone> = {
  none: "neutral",
  upcoming: "neutral",
  soon: "warn",
  today: "warn",
  packaged: "ok",
  overdue: "err",
};

export const TONE_COLOR: Record<DeadlineTone, string> = {
  neutral: "var(--fg-2)",
  warn: "var(--c-warn)",
  err: "var(--c-err)",
  ok: "var(--c-ok)",
};

/** Состояние, которое ещё зовёт действовать: его видно в списке и в строке точки. */
const ACTIVE: ReadonlySet<DeadlineState> = new Set([
  "upcoming",
  "soon",
  "today",
  "overdue",
]);

export const useDeadlineText = () => {
  const { t, i18n } = useTranslation("checkpointDeadline");

  /** «15.11, 23:59» по Москве. */
  const at = useCallback(
    (iso: string, now: number): string =>
      `${formatDeadlineDay(iso, now)}, ${formatDeadlineTime(iso)}`,
    [],
  );

  /** Строка срока на точке: «Срок: 15.11, 23:59 (через 3 дня)», «Сегодня до 23:59», … */
  const stateText = useCallback(
    (point: PointDeadline, now: number): string => {
      const { deadline, deadline_state: state, packaged_at } = point;
      if (deadline === null || state === "none") return t("state.none");
      const date = formatDeadlineDay(deadline, now);
      const time = formatDeadlineTime(deadline);
      const days = daysUntilDeadline(deadline, now) ?? 0;
      switch (state) {
        case "today":
          return t("state.today", { time });
        case "soon":
          // Страница открыта давно, а срок уже сегодня: пишем по календарю, не по старому ответу.
          return days > 0
            ? t("state.soon", { date, time, count: days })
            : t("state.today", { time });
        case "packaged":
          return t("state.packaged", {
            date,
            packed:
              packaged_at === null ? "" : formatDeadlineDay(packaged_at, now),
          });
        case "overdue":
          return t("state.overdue");
        case "upcoming":
          return t("state.upcoming", { date, time });
      }
    },
    [t],
  );

  /** Пометка проекта в списке: «Заявка на тему: через 3 дня»; null, если показывать нечего. */
  const listText = useCallback(
    (
      next: NextDeadline,
      now: number,
    ): { text: string; title: string; tone: DeadlineTone } | null => {
      if (!ACTIVE.has(next.state)) return null;
      const name = pickLocalized(next.name, i18n.language, next.profile_id);
      const date = formatDeadlineDay(next.deadline, now);
      const time = formatDeadlineTime(next.deadline);
      const days = daysUntilDeadline(next.deadline, now) ?? 0;
      if (next.state === "overdue") {
        return {
          text: t("list.overdue", { name }),
          title: t("list.overdueTitle", { date, time }),
          tone: "err",
        };
      }
      const title = t("list.title", { date, time });
      if (next.state === "today" || days <= 0) {
        return { text: t("list.today", { name }), title, tone: "warn" };
      }
      return {
        text: t("list.upcoming", { name, count: days }),
        title,
        tone: next.state === "soon" ? "warn" : "neutral",
      };
    },
    [i18n.language, t],
  );

  /** Коротко у точки в панели «Сдача»: «через 3 дня», «сегодня до 23:59», «просрочено». */
  const rowText = useCallback(
    (point: PointDeadline, now: number): string | null => {
      const { deadline, deadline_state: state } = point;
      if (deadline === null || !ACTIVE.has(state)) return null;
      if (state === "overdue") return t("row.overdue");
      const days = daysUntilDeadline(deadline, now) ?? 0;
      return state === "today" || days <= 0
        ? t("row.today", { time: formatDeadlineTime(deadline) })
        : t("row.upcoming", { count: days });
    },
    [t],
  );

  return useMemo(
    () => ({ at, stateText, listText, rowText }),
    [at, stateText, listText, rowText],
  );
};
