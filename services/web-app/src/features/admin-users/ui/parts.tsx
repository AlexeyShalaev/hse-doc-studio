import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Badge } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import type { AccountStatus } from "@entities/session";
import { failureKey, type Failure } from "../lib/failure";
import { initialsOf } from "../lib/format";

/** Круглый аватар с инициалами. */
export const Avatar = ({
  name,
  size = 28,
}: {
  name: string;
  size?: number;
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

const STATUS_VARIANT = {
  active: "success",
  pending_verification: "warning",
  pending_approval: "warning",
  disabled: "subtle",
} as const;

/** Состояние учётной записи чипом. */
export const StatusBadge = ({ status }: { status: AccountStatus }) => {
  const { t } = useTranslation("adminUsers");
  return (
    <Badge variant={STATUS_VARIANT[status]} data-testid={`status-${status}`}>
      {t(`status.${status}`)}
    </Badge>
  );
};

/** Сообщение об отказе из каталога ошибок. */
export const FailureNotice = ({ failure }: { failure: Failure }) => {
  const { t } = useTranslation("adminUsers");
  return (
    <div data-testid="users-failure">
      <Notice tone="err" role="alert" text={t(failureKey(failure.code))} />
    </div>
  );
};
