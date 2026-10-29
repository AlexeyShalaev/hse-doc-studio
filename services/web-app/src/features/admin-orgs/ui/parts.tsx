import type { CSSProperties, ReactNode } from "react";
import { Inbox } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Badge, Spinner } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import type { OrgRoleName } from "@entities/session";
import { failureKey, type Failure } from "../lib/failure";
import { initialsOf } from "../lib/format";

const ROLE_VARIANT = {
  owner: "accent",
  admin: "info",
  member: "subtle",
} as const;

/** Роль в организации чипом. */
export const RoleBadge = ({ role }: { role: OrgRoleName }) => {
  const { t } = useTranslation("adminOrgs");
  return (
    <Badge variant={ROLE_VARIANT[role]} data-testid={`role-${role}`}>
      {t(`role.${role}`)}
    </Badge>
  );
};

/** Круглый аватар с инициалами. */
export const Avatar = ({
  name,
  size = 28,
  style,
}: {
  name: string;
  size?: number;
  style?: CSSProperties;
}) => (
  <span
    aria-hidden="true"
    style={{
      width: size,
      height: size,
      borderRadius: "50%",
      background: "var(--bg-3)",
      border: "1px solid var(--border)",
      color: "var(--fg-1)",
      display: "inline-flex",
      alignItems: "center",
      justifyContent: "center",
      fontSize: Math.round(size * 0.38),
      fontWeight: 600,
      flexShrink: 0,
      ...style,
    }}
  >
    {initialsOf(name)}
  </span>
);

/** Человек: аватар, имя и почта. */
export const Person = ({
  name,
  email,
  badge,
}: {
  name: string;
  email: string;
  badge?: ReactNode;
}) => (
  <span className="flex items-center" style={{ gap: 10, minWidth: 0 }}>
    <Avatar name={name} />
    <span className="flex flex-col" style={{ minWidth: 0 }}>
      <span
        className="flex items-center"
        style={{ gap: 6, fontWeight: 500, fontSize: 13 }}
      >
        <span style={{ overflow: "hidden", textOverflow: "ellipsis" }}>
          {name}
        </span>
        {badge}
      </span>
      <span
        style={{
          color: "var(--fg-2)",
          fontSize: 11.5,
          overflow: "hidden",
          textOverflow: "ellipsis",
        }}
      >
        {email}
      </span>
    </span>
  </span>
);

/** Сообщение об отказе из каталога ошибок. */
export const FailureNotice = ({ failure }: { failure: Failure }) => {
  const { t } = useTranslation("adminOrgs");
  return (
    <div data-testid="orgs-failure">
      <Notice tone="err" role="alert" text={t(failureKey(failure.code))} />
    </div>
  );
};

export const LoadingRow = ({ testId }: { testId?: string }) => {
  const { t } = useTranslation("adminOrgs");
  return (
    <div
      className="flex items-center"
      style={{ gap: 8, fontSize: 12 }}
      data-testid={testId ?? "orgs-loading"}
      role="status"
    >
      <Spinner size="sm" />
      <span className="dim">{t("loading")}</span>
    </div>
  );
};

export const LoadFailed = ({
  text,
  onRetry,
}: {
  text: string;
  onRetry?: (() => void) | undefined;
}) => {
  const { t } = useTranslation("adminOrgs");
  return (
    <Notice
      tone="err"
      role="alert"
      text={text}
      action={
        onRetry && (
          <button type="button" className="btn xs" onClick={onRetry}>
            {t("retry")}
          </button>
        )
      }
    />
  );
};

/** Пустое состояние внутри карточки: значок, заголовок, пояснение и действие. */
export const EmptyBlock = ({
  icon,
  title,
  body,
  action,
  testId,
}: {
  icon?: ReactNode;
  title: string;
  body?: string;
  action?: ReactNode;
  testId?: string;
}) => (
  <div
    className="flex flex-col items-start"
    style={{
      gap: 8,
      padding: 20,
      border: "1px dashed var(--border)",
      borderRadius: "var(--r-2)",
    }}
    data-testid={testId}
  >
    <span style={{ color: "var(--fg-3)" }}>
      {icon ?? <Inbox size={18} aria-hidden="true" />}
    </span>
    <strong style={{ fontSize: 13 }}>{title}</strong>
    {body && (
      <span style={{ fontSize: 12, color: "var(--fg-2)", maxWidth: 480 }}>
        {body}
      </span>
    )}
    {action}
  </div>
);
