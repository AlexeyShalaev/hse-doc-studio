import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { FileText, Link2 } from "lucide-react";
import type { GuestInfo } from "@entities/session";
import { Badge, EmptyState } from "@shared/ui";

const target = (link: GuestInfo["links"][number]): string =>
  link.role === "reader" && !link.show_sources
    ? `/projects/${link.project_id}/view`
    : `/projects/${link.project_id}`;

/** Список проектов гостя (`guest-projects`): только содержимое, без шапки. */
export const GuestProjectsView = ({ guest }: { guest: GuestInfo }) => {
  const { t } = useTranslation("guest");
  const { t: tl } = useTranslation("shareLinks");
  return (
    <div
      className="flex flex-col"
      style={{
        gap: 16,
        padding: "32px 24px",
        maxWidth: 720,
        margin: "0 auto",
        width: "100%",
      }}
      data-testid="guest-projects"
    >
      <div>
        <h1 style={{ margin: 0, fontSize: 20, fontWeight: 600 }}>
          {t("home.title")}
        </h1>
        <p
          style={{
            margin: "6px 0 0",
            color: "var(--fg-2)",
            fontSize: 13,
            lineHeight: 1.5,
          }}
        >
          {t("home.lead")}
        </p>
      </div>
      {guest.links.length === 0 ? (
        <EmptyState framed title={t("home.empty")} icon={<Link2 size={22} />} />
      ) : (
        <ul
          className="flex flex-col"
          style={{ gap: 10, listStyle: "none", margin: 0, padding: 0 }}
        >
          {guest.links.map((link) => (
            <li
              key={link.project_id}
              className="flex items-center"
              style={{
                gap: 12,
                padding: 14,
                border: "1px solid var(--border)",
                borderRadius: "var(--r-3)",
                background: "var(--bg-1)",
              }}
            >
              <FileText
                size={18}
                aria-hidden="true"
                style={{ color: "var(--fg-2)" }}
              />
              <div
                className="flex flex-col"
                style={{ flex: 1, minWidth: 0, gap: 2 }}
              >
                <strong style={{ fontSize: 13.5 }}>{link.project_name}</strong>
                <span style={{ fontSize: 12, color: "var(--fg-2)" }}>
                  «{link.link_label}»
                </span>
              </div>
              <Badge variant="accent">{tl(`roles.${link.role}`)}</Badge>
              <Link
                to={target(link)}
                className="btn sm"
                data-testid={`guest-project-open-${link.project_id}`}
              >
                {t("home.open")}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};
