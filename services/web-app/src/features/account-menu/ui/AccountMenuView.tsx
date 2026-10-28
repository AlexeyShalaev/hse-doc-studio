import { LogOut, Settings, ShieldAlert, ShieldCheck } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Popover, PopoverContent, PopoverTrigger } from "@shared/ui/Popover";
import { Spinner } from "@shared/ui/Spinner";
import type { SessionUser } from "@entities/session";

export type AccountMenuViewProps = {
  user: SessionUser;
  pending?: boolean;
  /** Начальное состояние, нужно галерее. */
  defaultOpen?: boolean;
  onOpenSettings: () => void;
  /** Есть только при capabilities.admin: ссылка не показывается тому, кому админка ответит 404. */
  onOpenAdmin?: () => void;
  onLogout: () => void;
};

const Avatar = ({ initials, size }: { initials: string; size: number }) => (
  <span
    aria-hidden="true"
    className="flex items-center justify-center shrink-0 font-mono"
    style={{
      width: size,
      height: size,
      borderRadius: "50%",
      background: "var(--accent-soft, var(--bg-2))",
      color: "var(--accent)",
      boxShadow: "0 0 0 1px var(--accent-line)",
      fontSize: size > 28 ? 13 : 11,
      fontWeight: 600,
      textTransform: "uppercase",
    }}
  >
    {initials}
  </span>
);

const itemStyle = {
  width: "100%",
  justifyContent: "flex-start",
  padding: "7px 10px",
  gap: 8,
} as const;

/** Меню аккаунта: кто вошёл, настройки, выход. Чистый вид без запросов. */
export const AccountMenuView = ({
  user,
  pending = false,
  defaultOpen,
  onOpenSettings,
  onOpenAdmin,
  onLogout,
}: AccountMenuViewProps) => {
  const { t } = useTranslation("appChrome");
  return (
    <Popover {...(defaultOpen === undefined ? {} : { defaultOpen })}>
      <PopoverTrigger asChild>
        <button
          type="button"
          className="icon-btn tt"
          data-tt={t("accountMenu.title")}
          aria-label={t("accountMenu.open", { name: user.name })}
          data-testid="account-menu-trigger"
          style={{ width: 32, height: 32 }}
        >
          <Avatar initials={user.avatar_initials} size={24} />
        </button>
      </PopoverTrigger>
      <PopoverContent
        width={264}
        aria-label={t("accountMenu.title")}
        data-testid="account-menu"
      >
        <div
          className="flex items-center"
          style={{
            gap: 10,
            padding: 12,
            borderBottom: "1px solid var(--border)",
          }}
        >
          <Avatar initials={user.avatar_initials} size={36} />
          <div className="flex flex-col min-w-0" style={{ gap: 1 }}>
            <span
              className="truncate"
              style={{ fontSize: 13, fontWeight: 600, color: "var(--fg-0)" }}
            >
              {user.name}
            </span>
            <span
              className="truncate"
              style={{ fontSize: 11.5, color: "var(--fg-2)" }}
            >
              {user.email}
            </span>
          </div>
        </div>

        {(user.is_instance_admin || !user.email_verified) && (
          <div
            className="flex flex-wrap"
            style={{
              gap: 6,
              padding: "8px 12px 0",
            }}
          >
            {user.is_instance_admin && (
              <span className="chip" data-testid="account-menu-admin">
                {t("accountMenu.admin")}
              </span>
            )}
            {!user.email_verified && (
              <span
                className="chip"
                data-testid="account-menu-unverified"
                style={{ color: "var(--c-warn)" }}
              >
                <ShieldAlert size={10} />
                {t("accountMenu.unverified")}
              </span>
            )}
          </div>
        )}

        {user.org_roles.length > 0 && (
          <ul
            aria-label={t("accountMenu.orgs")}
            style={{
              listStyle: "none",
              margin: 0,
              padding: "8px 12px 0",
              fontSize: 11.5,
              color: "var(--fg-2)",
            }}
          >
            {user.org_roles.map((org) => (
              <li
                key={org.slug}
                className="flex items-center justify-between"
                style={{ gap: 8 }}
              >
                <span className="truncate">{org.name}</span>
                <span className="mono dim">
                  {t(`accountMenu.orgRole.${org.role}`)}
                </span>
              </li>
            ))}
          </ul>
        )}

        <div className="flex flex-col" style={{ padding: 6, marginTop: 6 }}>
          <button
            type="button"
            className="row-btn"
            style={itemStyle}
            onClick={onOpenSettings}
          >
            <Settings size={14} />
            {t("accountMenu.settings")}
          </button>
          {onOpenAdmin && (
            <button
              type="button"
              className="row-btn"
              style={itemStyle}
              onClick={onOpenAdmin}
              data-testid="account-menu-open-admin"
            >
              <ShieldCheck size={14} />
              {t("accountMenu.openAdmin")}
            </button>
          )}
          <button
            type="button"
            className="row-btn"
            style={itemStyle}
            disabled={pending}
            onClick={onLogout}
            data-testid="account-menu-logout"
          >
            {pending ? <Spinner size="sm" /> : <LogOut size={14} />}
            {t("accountMenu.logout")}
          </button>
        </div>
      </PopoverContent>
    </Popover>
  );
};
