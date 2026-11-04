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
  ArrowUpCircle,
  Bot,
  Building2,
  ChevronDown,
  ClipboardList,
  DatabaseBackup,
  DatabaseZap,
  Gauge,
  Globe,
  HardDrive,
  HeartPulse,
  KeyRound,
  LayoutDashboard,
  Plug,
  Server,
  ShieldCheck,
  SlidersHorizontal,
  Users,
  type LucideIcon,
} from "lucide-react";
import { Link, NavLink, Outlet, useLocation } from "react-router";
import { useTranslation } from "react-i18next";
import { useIsPhoneWidth } from "@shared/lib";
import { Modal, Tooltip, UiVariantContext } from "@shared/ui";
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
  | "backups"
  | "diagnostics"
  | "updates"
  | "data"
  | "instance"
  | "settings"
  | "signing"
  | "aiProviders"
  | "mcp"
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
      { id: "backups", to: "/admin/backups", icon: DatabaseBackup },
      { id: "updates", to: "/admin/updates", icon: ArrowUpCircle },
      { id: "data", to: "/admin/data", icon: DatabaseZap },
      { id: "diagnostics", to: "/admin/diagnostics", icon: HeartPulse },
    ],
  },
  {
    id: "settings",
    items: [
      { id: "instance", to: "/admin/instance", icon: Globe },
      { id: "settings", to: "/admin/settings", icon: SlidersHorizontal },
      { id: "signing", to: "/admin/signing", icon: KeyRound },
      { id: "aiProviders", to: "/admin/ai-providers", icon: Bot },
      { id: "mcp", to: "/admin/mcp", icon: Plug },
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
  data: "nav.count.data",
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

/** Раздел админки, который открыт по адресу: для подписи на кнопке меню телефона. */
const activeNavItem = (pathname: string): NavItem | undefined => {
  const items = ADMIN_NAV.flatMap((group) => group.items);
  return (
    items.find(
      (item) => item.id !== "overview" && pathname.startsWith(item.to),
    ) ?? items.find((item) => item.id === "overview")
  );
};

const AdminNav = () => {
  const { t } = useTranslation("adminShell");
  const narrow = useNarrow();
  const isPhone = useIsPhoneWidth();
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const { pathname } = useLocation();
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

  const head = (
    <div className="adm-nav-head">
      <WithTip narrow={narrow && !isPhone} label={name}>
        <span className="adm-nav-mark" aria-hidden="true">
          <ShieldCheck size="1rem" />
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
  );

  const groups = (
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
            const tipNarrow = narrow && !isPhone;
            return (
              <li key={id}>
                <WithTip
                  narrow={tipNarrow}
                  label={counterText ? `${label} · ${counterText}` : label}
                >
                  <NavLink
                    to={to}
                    end={id === "overview"}
                    data-testid={`admin-nav-${id}`}
                    aria-label={tipNarrow ? label : undefined}
                    className={({ isActive }) =>
                      `adm-nav-item${isActive ? " active" : ""}`
                    }
                    onClick={() => {
                      setIsMenuOpen(false);
                    }}
                  >
                    <Icon size="0.9375rem" aria-hidden="true" />
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
  );

  const foot = (
    <div className="adm-nav-foot">
      <WithTip narrow={narrow && !isPhone} label={t("nav.back")}>
        <Link
          to="/"
          className="adm-nav-item"
          data-testid="admin-back-to-studio"
          aria-label={narrow && !isPhone ? t("nav.back") : undefined}
        >
          <ArrowLeft size="0.9375rem" aria-hidden="true" />
          <span className="adm-nav-label">{t("nav.back")}</span>
        </Link>
      </WithTip>
      {bootstrap && (
        <div className="adm-nav-version" data-testid="admin-version">
          {t("nav.version", { version: bootstrap.version })}
        </div>
      )}
    </div>
  );

  // Телефон: рейка не помещается рядом с содержимым. Вместо неё кнопка с названием открытого
  // раздела над страницей, список разделов открывается шторкой.
  if (isPhone) {
    const current = activeNavItem(pathname);
    const CurrentIcon = current?.icon ?? LayoutDashboard;
    const currentCounter = current ? counters[current.id] : undefined;
    return (
      <>
        <Suspense fallback={null}>
          <NavStatusProbe onChange={report} />
        </Suspense>
        <div className="adm-phone-bar" data-testid="admin-nav">
          <button
            type="button"
            className="adm-phone-menu"
            data-testid="admin-menu-trigger"
            aria-haspopup="dialog"
            onClick={() => {
              setIsMenuOpen(true);
            }}
          >
            <CurrentIcon size={16} aria-hidden="true" />
            <span className="adm-phone-title">
              {current ? t(`nav.${current.id}`) : t("nav.label")}
            </span>
            {currentCounter && currentCounter.count > 0 && (
              <span className="adm-count" data-tone={currentCounter.tone}>
                {currentCounter.count}
              </span>
            )}
            <ChevronDown size="0.875rem" aria-hidden="true" />
          </button>
        </div>
        <Modal
          isOpen={isMenuOpen}
          onClose={() => {
            setIsMenuOpen(false);
          }}
          title={name}
        >
          <nav
            aria-label={t("nav.label")}
            className="adm-nav adm-nav--sheet"
            data-testid="admin-menu"
          >
            {groups}
            {foot}
          </nav>
        </Modal>
      </>
    );
  }

  return (
    <nav
      aria-label={t("nav.label")}
      className="adm-nav"
      data-testid="admin-nav"
    >
      <Suspense fallback={null}>
        <NavStatusProbe onChange={report} />
      </Suspense>
      {head}
      {groups}
      {foot}
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
      <div className="adm-body flex flex-1" style={{ minHeight: 0 }}>
        <AdminNav />
        <main className="adm-main">
          <Outlet />
        </main>
      </div>
    </UiVariantContext.Provider>
    <AppStatusBar />
  </div>
);
