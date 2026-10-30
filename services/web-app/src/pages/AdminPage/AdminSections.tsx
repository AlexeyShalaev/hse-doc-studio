import { Link } from "react-router";
import { useTranslation } from "react-i18next";
import { ADMIN_SECTIONS, type AdminSection } from "./AdminLayout";

const card = {
  border: "1px solid var(--border)",
  borderRadius: "var(--r-3)",
  background: "var(--bg-1)",
  boxShadow: "var(--shadow-1)",
} as const;

/** Начальная страница админки. Содержимое появится вместе с разделами. */
export const AdminOverview = () => {
  const { t } = useTranslation("adminShell");
  return (
    <div
      className="flex flex-col"
      style={{ gap: 20, maxWidth: 880 }}
      data-testid="admin-overview"
    >
      <header className="flex flex-col" style={{ gap: 4 }}>
        <h1 style={{ margin: 0, fontSize: 20, fontWeight: 600 }}>
          {t("overview.title")}
        </h1>
        <p style={{ margin: 0, fontSize: 13, color: "var(--fg-2)" }}>
          {t("overview.lead")}
        </p>
      </header>
      <ul
        aria-label={t("overview.cardsLabel")}
        style={{
          listStyle: "none",
          margin: 0,
          padding: 0,
          display: "grid",
          gap: 12,
          gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))",
        }}
      >
        {ADMIN_SECTIONS.filter((s) => s.id !== "overview").map(
          ({ id, to, icon: Icon }) => (
            <li key={id}>
              <Link
                to={to}
                className="flex flex-col"
                style={{
                  ...card,
                  gap: 8,
                  padding: 16,
                  height: "100%",
                  textDecoration: "none",
                  color: "inherit",
                }}
              >
                <span className="flex items-center" style={{ gap: 8 }}>
                  <Icon size={15} />
                  <span style={{ fontWeight: 600, fontSize: 13 }}>
                    {t(`nav.${id}`)}
                  </span>
                  <span className="chip subtle" style={{ marginLeft: "auto" }}>
                    {t("overview.open")}
                  </span>
                </span>
                <span style={{ fontSize: 12, color: "var(--fg-2)" }}>
                  {t(`sections.${id as Exclude<AdminSection, "overview">}`)}
                </span>
              </Link>
            </li>
          ),
        )}
      </ul>
    </div>
  );
};
