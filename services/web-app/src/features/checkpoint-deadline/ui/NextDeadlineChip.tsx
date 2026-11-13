import { useState, type CSSProperties } from "react";
import { CalendarClock } from "lucide-react";
import type { NextDeadline } from "@entities/session";
import { TONE_COLOR, useDeadlineText } from "../lib/useDeadlineText";

export type NextDeadlineChipProps = {
  next: NextDeadline | null | undefined;
  projectId: string;
  /** «Сейчас» для «через N дней»; по умолчанию время показа (галерея задаёт своё). */
  now?: number;
  /** Пометка в своей строке с этими отступами; без него просто чип. Пустой срок строки не даёт. */
  containerStyle?: CSSProperties;
};

/**
 * Ближайший срок проекта в списке (docs/design/signing-route.md, 16.2 и 16.6): «Заявка на тему:
 * через 3 дня», «сегодня», «просрочено». Руководитель видит то же у проектов студентов.
 */
export const NextDeadlineChip = ({
  next,
  projectId,
  now: fixedNow,
  containerStyle,
}: NextDeadlineChipProps) => {
  const [shownAt] = useState(() => Date.now());
  const text = useDeadlineText();
  if (!next) return null;
  const label = text.listText(next, fixedNow ?? shownAt);
  if (label === null) return null;
  const color = TONE_COLOR[label.tone];
  const chip = (
    <span
      className="chip"
      title={label.title}
      data-testid={`project-deadline-${projectId}`}
      data-state={next.state}
      style={{
        gap: "0.25rem",
        minWidth: 0,
        maxWidth: "100%",
        color,
        borderColor:
          label.tone === "neutral"
            ? undefined
            : `color-mix(in oklch, ${color} 30%, transparent)`,
        background:
          label.tone === "err"
            ? "var(--c-err-soft)"
            : label.tone === "warn"
              ? "var(--c-warn-soft)"
              : undefined,
      }}
    >
      <CalendarClock
        size="0.625rem"
        aria-hidden="true"
        style={{ flexShrink: 0 }}
      />
      <span className="truncate">{label.text}</span>
    </span>
  );
  return containerStyle ? (
    <div className="flex" style={{ minWidth: 0, ...containerStyle }}>
      {chip}
    </div>
  ) : (
    chip
  );
};
