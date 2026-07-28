import { clsx } from "clsx";

// .readiness-ring circle { stroke-width: 3 } живёт в index.css. viewBox равен
// размеру в пикселях, поэтому пользовательская единица = пиксель, а радиус
// уменьшен на половину обводки — иначе кольцо срезается краем svg.
const STROKE_WIDTH = 3;
const DEFAULT_SIZE = 28;

export type ReadinessRingProps = {
  done: number;
  total: number;
  size?: number;
  // Подпись собирает вызывающий: кольцо не знает ни про i18n, ни про то, что
  // именно оно считает — документы точки контроля или что-то ещё.
  label: string;
};

export const ReadinessRing = ({
  done,
  total,
  size = DEFAULT_SIZE,
  label,
}: ReadinessRingProps): React.JSX.Element => {
  const center = size / 2;
  const radius = Math.max(0, (size - STROKE_WIDTH) / 2);
  const circumference = 2 * Math.PI * radius;
  // total === 0 — считать нечего: рисуется одна дорожка, дуга не появляется, и
  // деления на ноль не происходит.
  const hasValue = total > 0;
  const ratio = hasValue ? Math.min(1, Math.max(0, done / total)) : 0;

  return (
    <svg
      className="readiness-ring"
      width={size}
      height={size}
      viewBox={`0 0 ${String(size)} ${String(size)}`}
      role="img"
      aria-label={label}
    >
      <circle className="readiness-track" cx={center} cy={center} r={radius} />
      {hasValue && (
        <circle
          className={clsx("readiness-value", done === total && "done")}
          cx={center}
          cy={center}
          r={radius}
          strokeDasharray={circumference}
          strokeDashoffset={circumference * (1 - ratio)}
        />
      )}
    </svg>
  );
};

ReadinessRing.displayName = "ReadinessRing";
