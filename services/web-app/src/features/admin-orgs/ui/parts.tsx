import type { CSSProperties } from "react";
import { useTranslation } from "react-i18next";
import { Notice } from "@shared/ui/ConflictKit";
import type { OrgRoleName } from "@entities/session";
import { failureKey, type Failure } from "../lib/failure";
import { orgInitials } from "../lib/format";
import "./adminOrgs.css";

/** Роль в организации пилюлей. */
export const RoleBadge = ({ role }: { role: OrgRoleName }) => {
  const { t } = useTranslation("adminOrgs");
  return (
    <span className="org-role" data-role={role} data-testid={`role-${role}`}>
      {t(`role.${role}`)}
    </span>
  );
};

const PALETTE = [
  "var(--chart-1)",
  "var(--chart-2)",
  "var(--chart-3)",
  "var(--chart-4)",
  "var(--chart-5)",
] as const;

const colorFor = (seed: string): string => {
  let hash = 0;
  for (const ch of seed) hash = (hash * 31 + ch.charCodeAt(0)) >>> 0;
  return PALETTE[hash % PALETTE.length] ?? PALETTE[0];
};

/** Знак организации: квадрат с инициалами, цвет не меняется вместе с названием. */
export const OrgMark = ({
  name,
  slug,
  size = 30,
}: {
  name: string;
  slug: string;
  size?: number;
}) => {
  const style: CSSProperties & Record<"--org-mark", string> = {
    width: size,
    height: size,
    fontSize: Math.max(10, Math.round(size * 0.38)),
    "--org-mark": colorFor(slug),
  };
  return (
    <span className="org-mark" aria-hidden="true" style={style}>
      {orgInitials(name)}
    </span>
  );
};

/** Сообщение об отказе из каталога ошибок. */
export const FailureNotice = ({ failure }: { failure: Failure }) => {
  const { t } = useTranslation("adminOrgs");
  return (
    <div data-testid="orgs-failure">
      <Notice tone="err" role="alert" text={t(failureKey(failure.code))} />
    </div>
  );
};
