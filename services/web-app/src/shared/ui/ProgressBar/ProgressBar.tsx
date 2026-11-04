export type ProgressBarProps = {
  /** null: доля неизвестна, полоса бегает без значения. */
  percent: number | null;
  label: string;
};

// Полоса хода работы: значение читает и скринридер.
export const ProgressBar = ({ percent, label }: ProgressBarProps) => (
  <div
    role="progressbar"
    aria-label={label}
    aria-valuemin={0}
    aria-valuemax={100}
    {...(percent === null ? {} : { "aria-valuenow": Math.round(percent) })}
    style={{
      height: "0.375rem",
      borderRadius: "62.4375rem",
      background: "var(--bg-3)",
      overflow: "hidden",
    }}
  >
    <div
      className={percent === null ? "animate-pulse" : undefined}
      style={{
        width:
          percent === null
            ? "40%"
            : `${String(Math.min(100, Math.max(0, percent)))}%`,
        height: "100%",
        borderRadius: "62.4375rem",
        background: "var(--accent)",
        transition: "width 300ms ease",
      }}
    />
  </div>
);
