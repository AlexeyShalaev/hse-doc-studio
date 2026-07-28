import type { DocumentStatus } from "@shared/api/types";
import { clsx } from "clsx";
import { useTranslation } from "react-i18next";

const sevClassByStatus: Record<DocumentStatus, string> = {
  draft: "",
  building: "info",
  ok: "ok",
  warn: "warn",
  err: "err",
  locked: "info",
};

const labelKeyByStatus: Record<DocumentStatus, string | null> = {
  draft: "statusBadge.draft",
  building: "statusBadge.building",
  ok: null,
  warn: "statusBadge.warn",
  err: "statusBadge.err",
  locked: "statusBadge.locked",
};

export type StatusBadgeProps = {
  status: DocumentStatus;
  className?: string;
};

export const StatusBadge = ({ status, className }: StatusBadgeProps) => {
  const { t } = useTranslation("uiPrimitives");
  const labelKey = labelKeyByStatus[status];
  const label = labelKey ? t(labelKey) : "OK";
  return (
    <span className={clsx("sev", sevClassByStatus[status], className)}>
      {label}
    </span>
  );
};

StatusBadge.displayName = "StatusBadge";
