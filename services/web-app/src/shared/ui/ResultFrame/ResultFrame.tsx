import type { ReactNode } from "react";
import {
  CircleCheck,
  Info,
  OctagonAlert,
  TriangleAlert,
  type LucideIcon,
} from "lucide-react";

// Рамка итога: значок и заголовок слева, пояснение и действия под ними. Общая
// для карточки проверки в окне подключения, мастера клонирования и импорта файла.

export type FrameTone = "ok" | "info" | "warn" | "err";

const TONE: Record<
  FrameTone,
  { icon: LucideIcon; color: string; soft: string }
> = {
  ok: { icon: CircleCheck, color: "var(--c-ok)", soft: "var(--c-ok-soft)" },
  info: { icon: Info, color: "var(--c-info)", soft: "var(--c-info-soft)" },
  warn: {
    icon: TriangleAlert,
    color: "var(--c-warn)",
    soft: "var(--c-warn-soft)",
  },
  err: {
    icon: OctagonAlert,
    color: "var(--c-err)",
    soft: "var(--c-err-soft)",
  },
};

export const ResultFrame = ({
  tone,
  title,
  children,
  actions,
  testId,
  role,
}: {
  tone: FrameTone;
  title: string;
  children?: ReactNode;
  actions?: ReactNode;
  testId: string;
  role?: "alert" | "status";
}) => {
  const { icon: Icon, color, soft } = TONE[tone];
  return (
    <section
      data-testid={testId}
      data-tone={tone}
      aria-label={title}
      role={role}
      style={{
        borderRadius: "var(--r-3)",
        border: `1px solid ${color}`,
        background: soft,
        padding: "0.75rem 0.875rem",
        display: "flex",
        flexDirection: "column",
        gap: "0.625rem",
      }}
    >
      <div className="flex items-start" style={{ gap: "0.5625rem" }}>
        <Icon
          size="1rem"
          aria-hidden="true"
          style={{ color, flexShrink: 0, marginTop: 1 }}
        />
        <h3
          style={{
            margin: 0,
            fontSize: "0.84375rem",
            fontWeight: 600,
            color: "var(--fg-0)",
            lineHeight: 1.35,
          }}
        >
          {title}
        </h3>
      </div>
      {children != null && (
        <div
          className="flex flex-col"
          style={{
            gap: "0.5rem",
            fontSize: "0.78125rem",
            lineHeight: 1.5,
            color: "var(--fg-1)",
            paddingLeft: "1.5625rem",
          }}
        >
          {children}
        </div>
      )}
      {actions != null && (
        <div
          className="flex items-center"
          style={{ gap: "0.5rem", flexWrap: "wrap", paddingLeft: "1.5625rem" }}
        >
          {actions}
        </div>
      )}
    </section>
  );
};

export const Facts = ({ items }: { items: [string, string][] }) => (
  <dl
    style={{
      margin: 0,
      display: "grid",
      gridTemplateColumns: "max-content 1fr",
      columnGap: "0.875rem",
      rowGap: "0.1875rem",
      fontSize: "0.75rem",
    }}
  >
    {items.map(([label, value]) => (
      <div key={label} style={{ display: "contents" }}>
        <dt className="dim">{label}</dt>
        <dd style={{ margin: 0, color: "var(--fg-0)", minWidth: 0 }}>
          {value}
        </dd>
      </div>
    ))}
  </dl>
);
