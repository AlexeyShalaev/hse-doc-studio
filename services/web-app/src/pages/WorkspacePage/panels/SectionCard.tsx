type SectionAccent = "default" | "err";

export type SectionCardProps = {
  title: string;
  fullSpan?: boolean;
  accent?: SectionAccent;
  children: React.ReactNode;
};

export const SectionCard = ({
  title,
  fullSpan,
  accent = "default",
  children,
}: SectionCardProps) => {
  return (
    <div
      className="card"
      style={{
        gridColumn: fullSpan ? "1 / -1" : undefined,
        padding: "1.125rem",
        display: "flex",
        flexDirection: "column",
        gap: "0.875rem",
      }}
    >
      <h3
        style={{
          margin: 0,
          fontSize: "0.8125rem",
          fontWeight: 600,
          color: accent === "err" ? "var(--c-err)" : "var(--fg-0)",
        }}
      >
        {title}
      </h3>
      {children}
    </div>
  );
};
