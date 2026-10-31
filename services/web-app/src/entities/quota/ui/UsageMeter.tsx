import { useTranslation } from "react-i18next";
import { Badge } from "@shared/ui";
import {
  formatBytes,
  formatCount,
  isByteKind,
  stateTone,
} from "../lib/quotaLib";
import type { UsageLine } from "../model/quota.schema";

const TONE_COLOR = {
  neutral: "var(--accent)",
  ok: "var(--c-ok)",
  warn: "var(--c-warn)",
  err: "var(--c-err)",
} as const;

const BADGE = {
  neutral: "default",
  ok: "success",
  warn: "warning",
  err: "error",
} as const;

/** Значение вида словами интерфейса: байты в единицах, остальное числом с разделителями. */
export const useQuantity = () => {
  const { t, i18n } = useTranslation("quota");
  const locale = i18n.language;
  const units = t("units.bytes", { returnObjects: true }) as string[];
  return (line: Pick<UsageLine, "kind">, value: number): string =>
    isByteKind(line.kind)
      ? formatBytes(value, units, locale)
      : formatCount(value, locale);
};

const dateOf = (iso: string, locale: string): string =>
  new Date(iso).toLocaleDateString(locale, {
    day: "numeric",
    month: "long",
    timeZone: "UTC",
  });

/** Одна строка использования: название, полоса, «использовано из предела», состояние и дата сброса. */
export const UsageMeter = ({ line }: { line: UsageLine }) => {
  const { t, i18n } = useTranslation("quota");
  const quantity = useQuantity();
  const tone = stateTone(line.state);
  const limited = line.limit !== null;
  const percent = line.percent ?? 0;
  const label = t(`kind.${line.kind}`);
  return (
    <div
      className="flex flex-col"
      style={{ gap: 6, padding: "10px 0" }}
      data-testid={`usage-${line.kind}`}
      data-state={line.state}
    >
      <div className="flex items-center" style={{ gap: 10 }}>
        <span style={{ fontWeight: 500, flex: 1 }}>{label}</span>
        <span
          className="tabular-nums"
          style={{ fontSize: 13, color: "var(--fg-2)" }}
        >
          {limited
            ? t("usedOf", {
                used: quantity(line, line.used),
                limit: quantity(line, line.limit ?? 0),
              })
            : t("usedNoLimit", { used: quantity(line, line.used) })}
        </span>
        {line.state === "warning" && (
          <Badge variant={BADGE[tone]}>{t("state.warning")}</Badge>
        )}
        {line.state === "exceeded" && (
          <Badge variant={BADGE[tone]}>{t("state.exceeded")}</Badge>
        )}
      </div>
      {limited && (
        <div
          role="progressbar"
          aria-label={label}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={percent}
          style={{
            height: 6,
            borderRadius: 999,
            background: "var(--bg-3)",
            overflow: "hidden",
          }}
        >
          <div
            style={{
              width: `${String(Math.max(percent, line.used > 0 ? 2 : 0))}%`,
              height: "100%",
              borderRadius: 999,
              background: TONE_COLOR[tone],
              transition: "width 300ms ease",
            }}
          />
        </div>
      )}
      <div style={{ fontSize: 12, color: "var(--fg-3)" }}>
        {line.source && t(`source.${line.source}`)}
        {line.source && line.resets_at && " · "}
        {line.resets_at &&
          t("resets", { date: dateOf(line.resets_at, i18n.language) })}
        {!line.source && !line.resets_at && t("noLimitHint")}
      </div>
    </div>
  );
};

/** Набор строк одного владельца в порядке видов. */
export const UsageList = ({
  lines,
  hideUnlimited = false,
}: {
  lines: readonly UsageLine[];
  hideUnlimited?: boolean;
}) => {
  const shown = hideUnlimited
    ? lines.filter((line) => line.limit !== null || line.used > 0)
    : lines;
  return (
    <div data-testid="usage-list">
      {shown.map((line) => (
        <UsageMeter key={`${line.scope}:${line.kind}`} line={line} />
      ))}
    </div>
  );
};
