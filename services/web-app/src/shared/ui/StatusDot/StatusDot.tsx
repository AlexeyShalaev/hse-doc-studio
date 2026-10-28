import { clsx } from "clsx";
import { useTranslation } from "react-i18next";

// Состояние ресурса (раннер, сервис): цветная точка и подпись. Цвет не
// единственный признак: у каждого состояния своя форма точки и свой текст, так
// что различимо и без цвета.

export type StatusDotStatus =
  "online" | "stale" | "offline" | "paused" | "degraded";

export type StatusDotProps = {
  status: StatusDotStatus;
  /** Своя подпись вместо стандартной. */
  label?: string;
  /** Только точка, подпись уходит в aria-label и подсказку. */
  hideLabel?: boolean;
  className?: string;
};

const COLOR: Record<StatusDotStatus, string> = {
  online: "var(--c-ok)",
  stale: "var(--c-warn)",
  offline: "var(--fg-3)",
  paused: "var(--c-info)",
  degraded: "var(--c-err)",
};

const Shape = ({ status }: { status: StatusDotStatus }) => {
  const color = COLOR[status];
  const common = { width: 10, height: 10, viewBox: "0 0 10 10" } as const;
  switch (status) {
    case "online":
      return (
        <svg {...common} aria-hidden="true">
          <circle cx="5" cy="5" r="4" fill={color} />
        </svg>
      );
    case "stale":
      return (
        <svg {...common} aria-hidden="true">
          <circle
            cx="5"
            cy="5"
            r="3.4"
            fill="none"
            stroke={color}
            strokeWidth="1.6"
          />
          <circle cx="5" cy="5" r="1.2" fill={color} />
        </svg>
      );
    case "offline":
      return (
        <svg {...common} aria-hidden="true">
          <circle
            cx="5"
            cy="5"
            r="3.5"
            fill="none"
            stroke={color}
            strokeWidth="1.6"
          />
        </svg>
      );
    case "paused":
      return (
        <svg {...common} aria-hidden="true">
          <rect x="1.5" y="1" width="2.4" height="8" rx="0.6" fill={color} />
          <rect x="6.1" y="1" width="2.4" height="8" rx="0.6" fill={color} />
        </svg>
      );
    case "degraded":
      return (
        <svg {...common} aria-hidden="true">
          <path d="M5 0.8 9.4 9H0.6z" fill={color} />
        </svg>
      );
  }
};

export const StatusDot = ({
  status,
  label,
  hideLabel = false,
  className,
}: StatusDotProps) => {
  const { t } = useTranslation("uiPrimitives");
  const text = label ?? t(`statusDot.${status}`);
  return (
    <span
      className={clsx(className)}
      data-status={status}
      title={hideLabel ? text : undefined}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        fontSize: 12.5,
        color: "var(--fg-1)",
        whiteSpace: "nowrap",
      }}
    >
      <span
        role={hideLabel ? "img" : undefined}
        aria-label={hideLabel ? text : undefined}
        style={{ display: "inline-flex", flexShrink: 0 }}
      >
        <Shape status={status} />
      </span>
      {!hideLabel && <span>{text}</span>}
    </span>
  );
};

StatusDot.displayName = "StatusDot";
