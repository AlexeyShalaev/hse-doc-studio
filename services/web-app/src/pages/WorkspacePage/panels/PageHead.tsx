import type { LucideIcon } from "lucide-react";

export type PageHeadProps = {
  icon: LucideIcon;
  title: string;
  sub?: string;
};

export const PageHead = ({ icon: Icon, title, sub }: PageHeadProps) => {
  return (
    <div className="flex items-center gap-3">
      <div
        className="flex items-center justify-center shrink-0"
        style={{
          width: "2.375rem",
          height: "2.375rem",
          borderRadius: "0.625rem",
          background: "var(--accent-soft)",
          color: "var(--accent)",
        }}
      >
        <Icon size="1.125rem" />
      </div>
      <div className="flex flex-col" style={{ gap: "0.125rem" }}>
        <h2
          style={{
            margin: 0,
            fontSize: "1.125rem",
            fontWeight: 600,
            letterSpacing: "-0.01em",
          }}
        >
          {title}
        </h2>
        {sub && (
          <p
            className="dim"
            style={{ margin: 0, fontSize: "0.78125rem", maxWidth: "40rem" }}
          >
            {sub}
          </p>
        )}
      </div>
    </div>
  );
};
