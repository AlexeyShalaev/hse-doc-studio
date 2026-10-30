import type { ReactNode } from "react";
import { Lock } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Badge, PageHeader } from "@shared/ui";

/** Карточка раздела настроек: заголовок с пояснением, справа статус, внизу содержимое. */
export const SettingsCard = ({
  id,
  title,
  sub,
  aside,
  testId,
  children,
}: {
  id?: string;
  title: string;
  sub?: string;
  aside?: ReactNode;
  testId?: string;
  children: ReactNode;
}) => (
  <section
    id={id}
    data-testid={testId}
    style={{
      padding: 16,
      borderRadius: "var(--r-3)",
      border: "1px solid var(--border)",
      background: "var(--bg-1)",
      boxShadow: "var(--shadow-1)",
      display: "flex",
      flexDirection: "column",
      gap: 14,
    }}
  >
    <div className="flex items-start" style={{ gap: 12 }}>
      <div className="flex flex-col" style={{ gap: 3, minWidth: 0, flex: 1 }}>
        <h2 style={{ margin: 0, fontSize: 14, fontWeight: 600 }}>{title}</h2>
        {sub && (
          <p style={{ margin: 0, color: "var(--fg-2)", fontSize: 12 }}>{sub}</p>
        )}
      </div>
      {aside}
    </div>
    {children}
  </section>
);

/** Значение задано окружением установки: на экране оно только для чтения. */
export const LockedBadge = ({ testId }: { testId?: string }) => {
  const { t } = useTranslation("adminInstall");
  return (
    <Badge variant="info" data-testid={testId ?? "locked-by-env"}>
      <Lock size={10} aria-hidden="true" style={{ marginRight: 4 }} />
      {t("locked.badge")}
    </Badge>
  );
};

/** Всё в карточке закрыто окружением. */
export const AllLockedNote = () => {
  const { t } = useTranslation("adminInstall");
  return (
    <p
      style={{
        margin: 0,
        fontSize: 12,
        color: "var(--fg-2)",
        lineHeight: 1.5,
      }}
      data-testid="all-locked-note"
    >
      {t("locked.note")}
    </p>
  );
};

/** Заголовок раздела админки. */
export const PageHead = ({ title, lead }: { title: string; lead: string }) => (
  <PageHeader title={title} description={lead} />
);
