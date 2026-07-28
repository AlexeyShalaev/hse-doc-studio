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
        padding: 18,
        display: "flex",
        flexDirection: "column",
        gap: 14,
      }}
    >
      <h3
        style={{
          margin: 0,
          fontSize: 13,
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
