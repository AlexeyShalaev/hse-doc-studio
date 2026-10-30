import { useId, useState } from "react";
import { CalendarDays, ChevronDown, X } from "lucide-react";
import { clsx } from "clsx";
import { useTranslation } from "react-i18next";
import { localeTag } from "../../lib/i18n/localeTag";
import { Popover, PopoverContent, PopoverTrigger } from "../Popover";
import { FilterTriggerText } from "./FilterMenu";

// Период для журналов (аудит, очередь): готовые отрезки и два поля дат.
// Значения — дни ГГГГ-ММ-ДД включительно; в запрос их переводит
// useListQueryState (filters: { from: { date: "from" }, to: { date: "to" } }).

export type DateRange = { from: string | null; to: string | null };

export type DateRangeFilterProps = {
  label?: string | undefined;
  value: DateRange;
  onChange: (value: DateRange) => void;
  testId?: string | undefined;
};

const PRESETS = [
  { id: "today", days: 0 },
  { id: "week", days: 6 },
  { id: "month", days: 29 },
  { id: "quarter", days: 89 },
] as const;

const pad = (n: number) => String(n).padStart(2, "0");
/** День в местном времени: ГГГГ-ММ-ДД. */
export const isoDay = (date: Date): string =>
  `${String(date.getFullYear())}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;

const daysAgo = (days: number): string => {
  const d = new Date();
  d.setDate(d.getDate() - days);
  return isoDay(d);
};

const shortDay = (day: string): string => {
  const [y, m, d] = day.split("-").map(Number);
  return new Date(y ?? 1970, (m ?? 1) - 1, d ?? 1).toLocaleDateString(
    localeTag(),
    { day: "numeric", month: "short" },
  );
};

export const DateRangeFilter = ({
  label,
  value,
  onChange,
  testId,
}: DateRangeFilterProps) => {
  const { t } = useTranslation("uiPrimitives");
  const [open, setOpen] = useState(false);
  const fromId = useId();
  const toId = useId();
  const title = label ?? t("dateRange.label");
  const today = isoDay(new Date());
  const preset = PRESETS.find(
    (p) =>
      value.from === daysAgo(p.days) &&
      (value.to === null || value.to === today),
  );
  const active = value.from !== null || value.to !== null;
  const summary = !active
    ? null
    : preset
      ? t(`dateRange.preset.${preset.id}`)
      : value.from && value.to
        ? t("dateRange.between", {
            from: shortDay(value.from),
            to: shortDay(value.to),
          })
        : value.from
          ? t("dateRange.since", { day: shortDay(value.from) })
          : t("dateRange.until", { day: shortDay(value.to ?? today) });

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <span className={clsx("fmenu", active && "is-active")}>
        <PopoverTrigger asChild>
          <button
            type="button"
            className="fmenu-trigger"
            aria-haspopup="dialog"
            data-testid={testId}
          >
            <CalendarDays size={13} aria-hidden="true" />
            <FilterTriggerText label={title} summary={summary} />
            <ChevronDown size={13} aria-hidden="true" />
          </button>
        </PopoverTrigger>
        {active && (
          <button
            type="button"
            className="fmenu-clear"
            aria-label={t("filterMenu.clearOne", { label: title })}
            title={t("filterMenu.clear")}
            onClick={() => {
              onChange({ from: null, to: null });
            }}
          >
            <X size={12} aria-hidden="true" />
          </button>
        )}
      </span>
      <PopoverContent width={280} align="start" aria-label={title}>
        <div className="drange">
          <div
            className="drange-presets"
            role="group"
            aria-label={t("dateRange.presets")}
          >
            {PRESETS.map((p) => (
              <button
                key={p.id}
                type="button"
                className={clsx("chip sans", preset?.id === p.id && "accent")}
                aria-pressed={preset?.id === p.id}
                onClick={() => {
                  onChange({ from: daysAgo(p.days), to: null });
                  setOpen(false);
                }}
              >
                {t(`dateRange.preset.${p.id}`)}
              </button>
            ))}
          </div>
          <div className="drange-fields">
            <label htmlFor={fromId}>{t("dateRange.from")}</label>
            <input
              id={fromId}
              type="date"
              className="input"
              value={value.from ?? ""}
              max={value.to ?? today}
              onChange={(event) => {
                onChange({ from: event.target.value || null, to: value.to });
              }}
            />
            <label htmlFor={toId}>{t("dateRange.to")}</label>
            <input
              id={toId}
              type="date"
              className="input"
              value={value.to ?? ""}
              min={value.from ?? undefined}
              max={today}
              onChange={(event) => {
                onChange({ from: value.from, to: event.target.value || null });
              }}
            />
          </div>
          {active && (
            <div className="fmenu-foot">
              <button
                type="button"
                className="btn ghost sm"
                onClick={() => {
                  onChange({ from: null, to: null });
                }}
              >
                {t("filterMenu.clear")}
              </button>
            </div>
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
};

DateRangeFilter.displayName = "DateRangeFilter";
