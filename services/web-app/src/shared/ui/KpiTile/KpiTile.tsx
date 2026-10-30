import type { ReactNode } from "react";
import { Link } from "react-router";
import { clsx } from "clsx";
import { useTranslation } from "react-i18next";

// Плитка сводки: подпись, крупное число, строка пояснения, по желанию полоса
// заполнения или спарклайн. С `to` плитка ведёт на раздел целиком.

export type KpiTone = "neutral" | "success" | "warning" | "danger" | "info";

const DOT: Record<Exclude<KpiTone, "neutral">, string> = {
  success: "ok",
  warning: "warn",
  danger: "err",
  info: "info",
};

export type KpiTileProps = {
  label: string;
  value: ReactNode;
  /** Единица рядом с числом мельче: «ГБ», «из 6». */
  unit?: ReactNode | undefined;
  /** Строка под числом: изменение, вторичное значение, состояние. */
  secondary?: ReactNode | undefined;
  /** Тон строки под числом. */
  tone?: KpiTone | undefined;
  icon?: ReactNode | undefined;
  /** Доля 0–100 полосой под числом. */
  progress?: number | null | undefined;
  progressTone?: KpiTone | undefined;
  /** Ряд значений для спарклайна (не меньше двух). */
  sparkline?: readonly number[] | undefined;
  /** Адрес раздела: плитка становится ссылкой. */
  to?: string | undefined;
  /** Данные ещё грузятся: вместо числа скелет. */
  loading?: boolean | undefined;
  /** Данные не пришли: короткий текст вместо числа. */
  error?: ReactNode | undefined;
  testId?: string | undefined;
  className?: string | undefined;
};

export const Sparkline = ({
  values,
  tone = "neutral",
  height = 28,
}: {
  values: readonly number[];
  tone?: KpiTone | undefined;
  height?: number | undefined;
}) => {
  if (values.length < 2) return null;
  const w = 100;
  const max = Math.max(...values);
  const min = Math.min(...values);
  const span = max - min || 1;
  const points = values.map((v, i) => {
    const x = (i / (values.length - 1)) * w;
    const y = height - 2 - ((v - min) / span) * (height - 4);
    return `${x.toFixed(2)},${y.toFixed(2)}`;
  });
  const color =
    tone === "success"
      ? "var(--c-ok)"
      : tone === "warning"
        ? "var(--c-warn)"
        : tone === "danger"
          ? "var(--c-err)"
          : "var(--accent)";
  return (
    <svg
      viewBox={`0 0 ${String(w)} ${String(height)}`}
      preserveAspectRatio="none"
      width="100%"
      height={height}
      aria-hidden="true"
      style={{ display: "block" }}
    >
      <polyline
        points={`0,${String(height)} ${points.join(" ")} ${String(w)},${String(height)}`}
        fill={color}
        opacity={0.12}
        stroke="none"
      />
      <polyline
        points={points.join(" ")}
        fill="none"
        stroke={color}
        strokeWidth={1.5}
        vectorEffect="non-scaling-stroke"
        strokeLinejoin="round"
      />
    </svg>
  );
};

/** Полоса заполнения в тон плитки. */
export const Meter = ({
  value,
  tone = "neutral",
  label,
}: {
  value: number;
  tone?: KpiTone | undefined;
  label: string;
}) => {
  const clamped = Math.min(100, Math.max(0, value));
  return (
    <div
      className="adm-meter"
      data-tone={tone}
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(clamped)}
    >
      <span style={{ width: `${String(clamped)}%` }} />
    </div>
  );
};

export const KpiTile = ({
  label,
  value,
  unit,
  secondary,
  tone = "neutral",
  icon,
  progress = null,
  progressTone,
  sparkline,
  to,
  loading = false,
  error,
  testId,
  className,
}: KpiTileProps) => {
  const { t } = useTranslation("uiPrimitives");
  const body = (
    <>
      <span className="adm-kpi-label">
        {icon}
        {label}
      </span>
      {loading ? (
        <span aria-label={t("adminKit.loading")} role="status">
          <span
            className="adm-skel"
            style={{ height: 24, width: "45%", margin: "3px 0" }}
          />
          <span className="adm-skel" style={{ width: "70%", marginTop: 8 }} />
        </span>
      ) : error ? (
        <span className="adm-kpi-sub" data-tone="danger" role="alert">
          {error}
        </span>
      ) : (
        <>
          <span className="adm-kpi-value">
            {value}
            {unit != null && <span className="adm-kpi-unit">{unit}</span>}
          </span>
          {progress != null && (
            <Meter value={progress} tone={progressTone ?? tone} label={label} />
          )}
          {sparkline && <Sparkline values={sparkline} tone={tone} />}
          {secondary != null && (
            <span className="adm-kpi-sub" data-tone={tone}>
              {tone !== "neutral" && (
                <span className={`dot ${DOT[tone]}`} aria-hidden="true" />
              )}
              {secondary}
            </span>
          )}
        </>
      )}
    </>
  );
  if (to) {
    return (
      <Link to={to} className={clsx("adm-kpi", className)} data-testid={testId}>
        {body}
      </Link>
    );
  }
  return (
    <div className={clsx("adm-kpi", className)} data-testid={testId}>
      {body}
    </div>
  );
};

/** Ряд плиток: сам подбирает число колонок по ширине. */
export const KpiGrid = ({ children }: { children: ReactNode }) => (
  <div className="adm-kpi-grid">{children}</div>
);

KpiTile.displayName = "KpiTile";
