import {
  ClipboardList,
  LayoutDashboard,
  Building2,
  Server,
  SlidersHorizontal,
  Users,
  type LucideIcon,
} from "lucide-react";
import { NavLink, Outlet } from "react-router";
import { useTranslation } from "react-i18next";
import { AppStatusBar } from "@widgets/AppStatusBar";
import { AppTitlebar } from "@widgets/AppTitlebar";

export type AdminSection =
  "overview" | "users" | "orgs" | "runners" | "settings" | "audit";

export const ADMIN_SECTIONS: readonly {
  id: AdminSection;
  to: string;
  icon: LucideIcon;
}[] = [
  { id: "overview", to: "/admin", icon: LayoutDashboard },
  { id: "users", to: "/admin/users", icon: Users },
  { id: "orgs", to: "/admin/orgs", icon: Building2 },
  { id: "runners", to: "/admin/runners", icon: Server },
  { id: "settings", to: "/admin/settings", icon: SlidersHorizontal },
  { id: "audit", to: "/admin/audit", icon: ClipboardList },
];

/** Каркас админки: заголовок приложения, левая навигация по разделам, содержимое. */
export const AdminLayout = () => {
  const { t } = useTranslation("adminShell");
  return (
    <div
      className="flex flex-col flex-1 bg-bg-0"
      style={{ minHeight: 0 }}
      data-testid="admin-layout"
    >
      <AppTitlebar />
      <div className="flex flex-1" style={{ minHeight: 0 }}>
        <nav
          aria-label={t("nav.label")}
          className="flex flex-col shrink-0"
          style={{
            width: 220,
            gap: 2,
            padding: 12,
            borderRight: "1px solid var(--border)",
            background: "var(--bg-1)",
            overflowY: "auto",
          }}
        >
          <div
            className="mono"
            style={{
              padding: "4px 10px 8px",
              fontSize: 10,
              letterSpacing: "0.1em",
              textTransform: "uppercase",
              color: "var(--fg-3)",
            }}
          >
            {t("title")}
          </div>
          {ADMIN_SECTIONS.map(({ id, to, icon: Icon }) => (
            <NavLink
              key={id}
              to={to}
              end={id === "overview"}
              data-testid={`admin-nav-${id}`}
              className={({ isActive }) =>
                `row-btn${isActive ? " active" : ""}`
              }
              style={{
                width: "100%",
                justifyContent: "flex-start",
                padding: "7px 10px",
                gap: 8,
              }}
            >
              <Icon size={14} />
              {t(`nav.${id}`)}
            </NavLink>
          ))}
        </nav>
        <main
          className="flex flex-col flex-1"
          style={{ minWidth: 0, overflowY: "auto", padding: 24 }}
        >
          <Outlet />
        </main>
      </div>
      <AppStatusBar />
    </div>
  );
};
