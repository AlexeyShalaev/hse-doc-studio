import type { ReactNode } from "react";

/** Карточка раздела «Аккаунт»: заголовок с пояснением и содержимое. */
export const AccountCard = ({
  id,
  title,
  sub,
  testId,
  children,
}: {
  id?: string;
  title: string;
  sub?: string;
  testId?: string;
  children: ReactNode;
}) => (
  <section
    id={id}
    data-testid={testId}
    className={id ? "settings-anchor" : undefined}
    style={{
      padding: 16,
      borderRadius: "var(--r-3)",
      border: "1px solid var(--border)",
      background: "var(--bg-1)",
      display: "flex",
      flexDirection: "column",
      gap: 12,
    }}
  >
    <div className="flex flex-col" style={{ gap: 3 }}>
      <h5 style={{ margin: 0, fontSize: 13.5, fontWeight: 600 }}>{title}</h5>
      {sub && (
        <p style={{ margin: 0, color: "var(--fg-2)", fontSize: 12 }}>{sub}</p>
      )}
    </div>
    {children}
  </section>
);
