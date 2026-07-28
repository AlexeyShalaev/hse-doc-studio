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
          width: 38,
          height: 38,
          borderRadius: 10,
          background: "var(--accent-soft)",
          color: "var(--accent)",
        }}
      >
        <Icon size={18} />
      </div>
      <div className="flex flex-col" style={{ gap: 2 }}>
        <h2
          style={{
            margin: 0,
            fontSize: 18,
            fontWeight: 600,
            letterSpacing: "-0.01em",
          }}
        >
          {title}
        </h2>
        {sub && (
          <p
            className="dim"
            style={{ margin: 0, fontSize: 12.5, maxWidth: 640 }}
          >
            {sub}
          </p>
        )}
      </div>
    </div>
  );
};
