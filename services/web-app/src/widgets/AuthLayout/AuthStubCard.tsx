import { Link } from "react-router";
import { useTranslation } from "react-i18next";

export type AuthStubLink = { to: string; label: string };

export type AuthStubCardProps = {
  /** Ключ экрана в пространстве auth: pages.<screen>.title / .body. */
  screen: string;
  links?: readonly AuthStubLink[];
};

/**
 * Заглушка экрана без сессии: заголовок, пояснение и ссылки на соседние
 * экраны. Настоящее содержимое приходит срезами входа, регистрации и мастера.
 */
export const AuthStubCard = ({ screen, links = [] }: AuthStubCardProps) => {
  const { t } = useTranslation("auth");
  return (
    <section data-testid={`auth-screen-${screen}`}>
      <h1 style={{ fontSize: 20, fontWeight: 600, margin: "0 0 8px" }}>
        {t(`pages.${screen}.title`)}
      </h1>
      <p style={{ margin: 0, color: "var(--fg-2)", fontSize: 13.5 }}>
        {t(`pages.${screen}.body`)}
      </p>
      {links.length > 0 && (
        <nav
          className="flex flex-col"
          style={{ gap: 8, marginTop: 20, fontSize: 13 }}
        >
          {links.map((link) => (
            <Link key={link.to} to={link.to} style={{ color: "var(--accent)" }}>
              {link.label}
            </Link>
          ))}
        </nav>
      )}
    </section>
  );
};
