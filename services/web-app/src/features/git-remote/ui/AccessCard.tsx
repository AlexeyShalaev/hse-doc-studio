import type { ReactNode } from "react";

export type AccessCardProps = {
  /** Якорь для поиска по настройкам и для связи заголовка с областью. */
  id: string;
  title: string;
  description?: ReactNode;
  children: ReactNode;
};

// Блок раздела «Доступ к репозиториям»: заголовок, пояснение, содержимое.
export const AccessCard = ({
  id,
  title,
  description,
  children,
}: AccessCardProps) => (
  <section
    id={id}
    aria-labelledby={`${id}-title`}
    className="settings-anchor flex flex-col"
    style={{
      gap: 12,
      padding: 16,
      borderRadius: "var(--r-3)",
      border: "1px solid var(--border)",
      background: "var(--bg-1)",
    }}
  >
    <header className="flex flex-col" style={{ gap: 3 }}>
      <h5
        id={`${id}-title`}
        style={{ margin: 0, fontSize: 13, fontWeight: 600 }}
      >
        {title}
      </h5>
      {description && (
        <p
          className="dim"
          style={{ margin: 0, fontSize: 11.5, lineHeight: 1.55 }}
        >
          {description}
        </p>
      )}
    </header>
    {children}
  </section>
);
