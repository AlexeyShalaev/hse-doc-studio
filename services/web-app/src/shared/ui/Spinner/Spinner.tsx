import { clsx } from "clsx";
import { useTranslation } from "react-i18next";

export type SpinnerProps = {
  size?: "sm" | "md" | "lg";
  className?: string;
};

const SIZE_PX: Record<NonNullable<SpinnerProps["size"]>, number> = {
  sm: 14,
  md: 20,
  lg: 36,
};

const STROKE: Record<NonNullable<SpinnerProps["size"]>, number> = {
  sm: 2,
  md: 2.4,
  lg: 3,
};

// Pure-SVG spinner. The border-based approach wobbles on rotation because the
// browser's border anti-aliasing isn't sub-pixel stable per angle; strokes on
// SVG circles are.
export const Spinner = ({ size = "md", className }: SpinnerProps) => {
  const { t } = useTranslation("uiPrimitives");
  const px = SIZE_PX[size];
  const stroke = STROKE[size];
  const r = 12 - stroke / 2 - 0.5;
  const circumference = 2 * Math.PI * r;
  const arcLength = circumference * 0.25;
  const gap = circumference - arcLength;

  return (
    <span
      role="status"
      aria-label={t("spinner.loading")}
      className={clsx("spin", className)}
      style={{
        display: "inline-flex",
        width: px,
        height: px,
        color: "var(--accent)",
        flexShrink: 0,
      }}
    >
      <svg
        viewBox="0 0 24 24"
        width={px}
        height={px}
        style={{ display: "block" }}
      >
        <circle
          cx="12"
          cy="12"
          r={r}
          fill="none"
          stroke="currentColor"
          strokeOpacity="0.18"
          strokeWidth={stroke}
        />
        <circle
          cx="12"
          cy="12"
          r={r}
          fill="none"
          stroke="currentColor"
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={`${arcLength.toFixed(2)} ${gap.toFixed(2)}`}
          transform="rotate(-90 12 12)"
        />
      </svg>
    </span>
  );
};

Spinner.displayName = "Spinner";
