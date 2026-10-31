import type { QuotaKind, QuotaState, UsageLine } from "../model/quota.schema";

const KB = 1024;

/** Размер в байтах словами интерфейса: «1,1 ГБ». Единицы приходят из словаря. */
export const formatBytes = (
  bytes: number,
  units: readonly string[],
  locale: string,
): string => {
  let size = bytes;
  let index = 0;
  while (size >= KB && index < units.length - 1) {
    size /= KB;
    index += 1;
  }
  const digits = size >= 10 || Number.isInteger(size) ? 0 : 1;
  return `${size.toLocaleString(locale, { maximumFractionDigits: digits })} ${units[index] ?? ""}`;
};

export const formatCount = (value: number, locale: string): string =>
  value.toLocaleString(locale);

export const isByteKind = (kind: QuotaKind): boolean => kind === "storage";

/** Порядок видов на экранах: место, сборки, ИИ, участники. */
export const KIND_ORDER: readonly QuotaKind[] = [
  "storage",
  "builds",
  "ai_tokens_day",
  "ai_tokens_month",
  "members",
];

export const stateTone = (
  state: QuotaState,
): "neutral" | "ok" | "warn" | "err" =>
  state === "exceeded"
    ? "err"
    : state === "warning"
      ? "warn"
      : state === "ok"
        ? "ok"
        : "neutral";

/** Самая тревожная строка из набора: для значка в шапке и сводки. */
export const worstState = (lines: readonly UsageLine[]): QuotaState => {
  const order: QuotaState[] = ["unlimited", "ok", "warning", "exceeded"];
  return lines.reduce<QuotaState>(
    (worst, line) =>
      order.indexOf(line.state) > order.indexOf(worst) ? line.state : worst,
    "unlimited",
  );
};
