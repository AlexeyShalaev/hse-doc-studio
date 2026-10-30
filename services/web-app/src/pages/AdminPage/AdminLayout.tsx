import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import {
  Activity,
  ArrowLeft,
  Bot,
  Building2,
  ClipboardList,
  Gauge,
  Globe,
  HardDrive,
  KeyRound,
  LayoutDashboard,
  Server,
  ShieldCheck,
  SlidersHorizontal,
  Users,
  type LucideIcon,
} from "lucide-react";
import { Link, NavLink, Outlet } from "react-router";
import { useTranslation } from "react-i18next";
import { Tooltip, UiVariantContext } from "@shared/ui";
import { useBootstrap } from "@entities/session";
import { AppStatusBar } from "@widgets/AppStatusBar";
import { AppTitlebar } from "@widgets/AppTitlebar";
import type { NavStatus } from "./navStatus";

// Счётчики и название установки считаются в отдельном чанке: запросы разделов
// не утяжеляют оболочку.
const NavStatusProbe = lazy(() =>
  import("./navStatus").then((m) => ({ default: m.NavStatusProbe })),
);

export type AdminSection =
  | "overview"
  | "users"
  | "orgs"
  | "runners"
  | "quotas"
  | "services"
  | "storage"
  | "instance"
  | "settings"
  | "signing"
  | "aiProviders"
  | "audit";

type NavItem = { id: AdminSection; to: string; icon: LucideIcon };
type NavGroup = {
  id: "main" | "people" | "builds" | "system" | "settings" | "log";
  items: readonly NavItem[];
};

const ADMIN_NAV: readonly NavGroup[] = [
  {
    id: "main",
    items: [{ id: "overview", to: "/admin", icon: LayoutDashboard }],
  },
  {
    id: "people",
    items: [
      { id: "users", to: "/admin/users", icon: Users },
      { id: "orgs", to: "/admin/orgs", icon: Building2 },
    ],
  },
  {
    id: "builds",
    items: [
      { id: "runners", to: "/admin/runners", icon: Server },
      { id: "quotas", to: "/admin/quotas", icon: Gauge },
    ],
  },
  {
    id: "system",
    items: [
      { id: "services", to: "/admin/services", icon: Activity },
      { id: "storage", to: "/admin/storage", icon: HardDrive },
    ],
  },
  {
    id: "settings",
    items: [
      { id: "instance", to: "/admin/instance", icon: Globe },
      { id: "settings", to: "/admin/settings", icon: SlidersHorizontal },
      { id: "signing", to: "/admin/signing", icon: KeyRound },
      { id: "aiProviders", to: "/admin/ai-providers", icon: Bot },
    ],
  },
  {
    id: "log",
    items: [{ id: "audit", to: "/admin/audit", icon: ClipboardList }],
  },
];

const NARROW = "(max-width: 1024px)";

/** На узком окне навигация сжимается до значков: подписи переезжают в подсказки. */
const useNarrow = (): boolean => {
  const [narrow, setNarrow] = useState(
    () => typeof window !== "undefined" && window.matchMedia(NARROW).matches,
  );
  useEffect(() => {
    const media = window.matchMedia(NARROW);
    const onChange = () => {
      setNarrow(media.matches);
    };
    media.addEventListener("change", onChange);
    return () => {
      media.removeEventListener("change", onChange);
    };
  }, []);
  return narrow;
};

const COUNTER_KEY: Record<string, string> = {
  users: "nav.count.users",
  runners: "nav.count.runners",
  services: "nav.count.services",
  storage: "nav.count.storage",
};

const WithTip = ({
  narrow,
  label,
  children,
}: {
  narrow: boolean;
  label: string;
  children: ReactNode;
}) =>
  narrow ? (
    <Tooltip content={label} side="right" delayDuration={150}>
      {/* Обёртка, а не сам NavLink: Slot подсказки склеил бы его className-функцию в строку. */}
      <span style={{ display: "block" }}>{children}</span>
    </Tooltip>
  ) : (
    children
  );

const AdminNav = () => {
  const { t } = useTranslation("adminShell");
  const narrow = useNarrow();
  const [status, setStatus] = useState<NavStatus>({
    counters: {},
    instanceName: null,
    instanceHost: null,
  });
  const report = useCallback((next: NavStatus) => {
    setStatus(next);
  }, []);
  const counters: Partial<
    Record<AdminSection, NavStatus["counters"]["users"]>
  > = status.counters;
  const bootstrap = useBootstrap().data;
  const name = status.instanceName ?? t("nav.instanceFallback");

  return (
    <nav
      aria-label={t("nav.label")}
      className="adm-nav"
      data-testid="admin-nav"
    >
      <Suspense fallback={null}>
        <NavStatusProbe onChange={report} />
      </Suspense>
      <div className="adm-nav-head">
        <WithTip narrow={narrow} label={name}>
          <span className="adm-nav-mark" aria-hidden="true">
            <ShieldCheck size={16} />
          </span>
        </WithTip>
        <div className="adm-nav-head-text" style={{ minWidth: 0, flex: 1 }}>
          <div className="adm-nav-title" data-testid="admin-instance-name">
            {name}
          </div>
          {status.instanceHost && (
            <div className="adm-nav-who" data-testid="admin-instance-host">
              <span>{status.instanceHost}</span>
            </div>
          )}
        </div>
      </div>
      <div className="adm-nav-scroll">
        {ADMIN_NAV.map((group) => (
          <ul
            key={group.id}
            className="adm-nav-group"
            aria-labelledby={
              group.id === "main" ? undefined : `admin-nav-g-${group.id}`
            }
          >
            {group.id !== "main" && (
              <li
                id={`admin-nav-g-${group.id}`}
                className="adm-nav-caption"
                role="presentation"
              >
                {t(`nav.groups.${group.id}`)}
              </li>
            )}
            {group.items.map(({ id, to, icon: Icon }) => {
              const label = t(`nav.${id}`);
              const counter = counters[id];
              const key = COUNTER_KEY[id];
              const counterText =
                counter && key ? t(key, { count: counter.count }) : null;
              return (
                <li key={id}>
                  <WithTip
                    narrow={narrow}
                    label={counterText ? `${label} · ${counterText}` : label}
                  >
                    <NavLink
                      to={to}
                      end={id === "overview"}
                      data-testid={`admin-nav-${id}`}
                      aria-label={narrow ? label : undefined}
                      className={({ isActive }) =>
                        `adm-nav-item${isActive ? " active" : ""}`
                      }
                    >
                      <Icon size={15} aria-hidden="true" />
                      <span className="adm-nav-label">{label}</span>
                      {counter && (
                        <span
                          className="adm-count"
                          data-tone={counter.tone}
                          data-dot={counter.count === 0 || undefined}
                          data-testid={`admin-nav-count-${id}`}
                          title={counterText ?? undefined}
                        >
                          {counter.count > 0 && (
                            <span aria-hidden="true">{counter.count}</span>
                          )}
                          {counterText && (
                            <span className="sr-only">{counterText}</span>
                          )}
                        </span>
                      )}
                    </NavLink>
                  </WithTip>
                </li>
              );
            })}
          </ul>
        ))}
      </div>
      <div className="adm-nav-foot">
        <WithTip narrow={narrow} label={t("nav.back")}>
          <Link
            to="/"
            className="adm-nav-item"
            data-testid="admin-back-to-studio"
            aria-label={narrow ? t("nav.back") : undefined}
          >
            <ArrowLeft size={15} aria-hidden="true" />
            <span className="adm-nav-label">{t("nav.back")}</span>
          </Link>
        </WithTip>
        {bootstrap && (
          <div className="adm-nav-version" data-testid="admin-version">
            {t("nav.version", { version: bootstrap.version })}
          </div>
        )}
      </div>
    </nav>
  );
};

/** Каркас админки: заголовок приложения, сгруппированная навигация, содержимое. */
export const AdminLayout = () => (
  <div
    className="adm-shell ui-console flex flex-col flex-1 bg-bg-0"
    style={{ minHeight: 0 }}
    data-testid="admin-layout"
  >
    <UiVariantContext.Provider value="console">
      <AppTitlebar showVersion={false} />
      <div className="flex flex-1" style={{ minHeight: 0 }}>
        <AdminNav />
        <main className="adm-main">
          <Outlet />
        </main>
      </div>
    </UiVariantContext.Provider>
    <AppStatusBar />
  </div>
);
