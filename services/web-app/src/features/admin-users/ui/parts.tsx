import { ShieldCheck } from "lucide-react";
import { useTranslation } from "react-i18next";
import { formatPastTime, formatRelativeTime } from "@shared/lib";
import { StatusDot, type StatusDotStatus } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import type { AccountStatus } from "@entities/session";
import { failureKey, type Failure } from "../lib/failure";
import { formatFull } from "../lib/format";
import "./adminUsers.css";

// Одобрение ждёт администратора, подтверждение почты ждёт самого человека.
const STATUS_TONE: Record<AccountStatus, StatusDotStatus> = {
  active: "success",
  pending_verification: "info",
  pending_approval: "warning",
  disabled: "neutral",
};

/** Состояние учётной записи: точка и подпись. */
export const AccountStatusLabel = ({ status }: { status: AccountStatus }) => {
  const { t } = useTranslation("adminUsers");
  return (
    <span data-testid={`status-${status}`}>
      <StatusDot status={STATUS_TONE[status]} label={t(`status.${status}`)} />
    </span>
  );
};

/** Роль на установке: администратор пилюлей, остальные спокойным текстом. */
export const RoleLabel = ({ isAdmin }: { isAdmin: boolean }) => {
  const { t } = useTranslation("adminUsers");
  return isAdmin ? (
    <span className="ppl-role">
      <ShieldCheck size={12} aria-hidden="true" />
      {t("users.admin")}
    </span>
  ) : (
    <span className="ppl-muted">{t("users.member")}</span>
  );
};

/** Момент относительно сейчас («2 дня назад»); точное время в подсказке. */
export const When = ({
  iso,
  empty,
  future = false,
}: {
  iso: string | null;
  /** Подпись, когда времени нет («не входил»). */
  empty?: string;
  /** Срок впереди («через 5 дней»). */
  future?: boolean;
}) => {
  const { i18n } = useTranslation("adminUsers");
  if (!iso) return <span className="ppl-faint">{empty ?? ""}</span>;
  return (
    <time
      dateTime={iso}
      title={formatFull(iso, i18n.language)}
      className="ppl-nowrap"
    >
      {future ? formatRelativeTime(iso) : formatPastTime(iso)}
    </time>
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
