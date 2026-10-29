import { useId, useState, type ReactNode } from "react";
import {
  ArrowLeft,
  FolderKanban,
  Gauge,
  Trash2,
  UsersRound,
  Users,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { Badge, Button, ConfirmByName } from "@shared/ui";
import type { AdminOrg } from "@entities/session";
import type { Failure } from "../lib/failure";
import { CARD } from "../lib/styles";
import { LoadFailed, LoadingRow, RoleBadge } from "./parts";

export type OrgTab = "members" | "groups";

/** Вкладки, которых ещё нет: ведут на этапы 3 и 4, данных у них нет. */
const SOON_TABS = [
  { id: "projects", icon: FolderKanban },
  { id: "quotas", icon: Gauge },
] as const;

export type OrgDetailViewProps = {
  status: "loading" | "error" | "missing" | "ready";
  org: AdminOrg | null;
  tab: OrgTab;
  onTab: (tab: OrgTab) => void;
  onBack: () => void;
  onRetry?: () => void;
  /** Только админ установки удаляет организацию. */
  canDelete: boolean;
  deleting?: boolean;
  deleteFailure?: Failure | null;
  onDelete: () => void;
  onDeleteReset?: () => void;
  /** Содержимое открытой вкладки. */
  children?: ReactNode;
};

/** Страница организации: шапка, вкладки и удаление. */
export const OrgDetailView = ({
  status,
  org,
  tab,
  onTab,
  onBack,
  onRetry,
  canDelete,
  deleting = false,
  deleteFailure = null,
  onDelete,
  onDeleteReset,
  children,
}: OrgDetailViewProps) => {
  const { t } = useTranslation("adminOrgs");
  const [confirming, setConfirming] = useState(false);
  const panelId = useId();

  const back = (
    <Button
      variant="ghost"
      size="sm"
      type="button"
      onClick={onBack}
      style={{ gap: 6, alignSelf: "flex-start" }}
      data-testid="org-back"
    >
      <ArrowLeft size={14} aria-hidden="true" />
      {t("detail.back")}
    </Button>
  );

  if (status === "loading") {
    return (
      <div className="flex flex-col" style={{ gap: 14 }}>
        {back}
        <LoadingRow />
      </div>
    );
  }
  if (status === "error") {
    return (
      <div className="flex flex-col" style={{ gap: 14 }}>
        {back}
        <LoadFailed text={t("detail.loadFailed")} onRetry={onRetry} />
      </div>
    );
  }
  if (status === "missing" || !org) {
    return (
      <div className="flex flex-col" style={{ gap: 14 }}>
        {back}
        <section
          style={{ ...CARD, padding: 24, maxWidth: 520 }}
          className="flex flex-col"
          data-testid="org-missing"
        >
          <h1 style={{ margin: 0, fontSize: 17, fontWeight: 600 }}>
            {t("detail.missing.title")}
          </h1>
          <p
            style={{ margin: "6px 0 0", fontSize: 12.5, color: "var(--fg-2)" }}
          >
            {t("detail.missing.body")}
          </p>
        </section>
      </div>
    );
  }

  const tabs: { id: OrgTab; icon: typeof Users; count: number | null }[] = [
    { id: "members", icon: Users, count: org.member_count },
    { id: "groups", icon: UsersRound, count: null },
  ];

  return (
    <div className="flex flex-col" style={{ gap: 16 }} data-testid="org-detail">
      {back}
      <header className="flex items-start" style={{ gap: 12 }}>
        <div className="flex flex-col" style={{ gap: 6, flex: 1, minWidth: 0 }}>
          <h1 style={{ margin: 0, fontSize: 20, fontWeight: 600 }}>
            {org.name}
          </h1>
          <div
            className="flex items-center"
            style={{ gap: 8, flexWrap: "wrap" }}
          >
            <span
              className="mono"
              style={{ fontSize: 12, color: "var(--fg-2)" }}
            >
              {org.slug}
            </span>
            {org.my_role ? (
              <RoleBadge role={org.my_role} />
            ) : (
              <Badge variant="subtle">{t("list.instanceAdmin")}</Badge>
            )}
            <span style={{ fontSize: 12, color: "var(--fg-2)" }}>
              {t("detail.stats", {
                members: org.member_count,
                projects: org.project_count,
              })}
            </span>
          </div>
        </div>
        {canDelete && (
          <Button
            variant="outline"
            size="sm"
            type="button"
            style={{ gap: 6 }}
            data-testid="org-delete"
            onClick={() => {
              onDeleteReset?.();
              setConfirming(true);
            }}
          >
            <Trash2 size={14} aria-hidden="true" />
            {t("detail.delete.button")}
          </Button>
        )}
      </header>

      <div
        role="tablist"
        aria-label={t("detail.tabs.label")}
        className="flex"
        style={{
          gap: 4,
          borderBottom: "1px solid var(--border)",
          flexWrap: "wrap",
        }}
      >
        {tabs.map(({ id, icon: Icon, count }) => (
          <button
            key={id}
            type="button"
            role="tab"
            id={`${panelId}-tab-${id}`}
            aria-selected={tab === id}
            aria-controls={`${panelId}-panel`}
            data-testid={`org-tab-${id}`}
            className={`row-btn${tab === id ? " active" : ""}`}
            style={{
              padding: "8px 12px",
              gap: 6,
              borderRadius: "var(--r-2) var(--r-2) 0 0",
            }}
            onClick={() => {
              onTab(id);
            }}
          >
            <Icon size={14} aria-hidden="true" />
            {t(`detail.tabs.${id}`)}
            {count !== null && (
              <span className="chip subtle" style={{ marginLeft: 2 }}>
                {count}
              </span>
            )}
          </button>
        ))}
        {SOON_TABS.map(({ id, icon: Icon }) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={false}
            aria-disabled="true"
            tabIndex={-1}
            data-testid={`org-tab-${id}`}
            title={t("detail.tabs.soonHint")}
            className="row-btn"
            style={{
              padding: "8px 12px",
              gap: 6,
              opacity: 0.55,
              cursor: "not-allowed",
              borderRadius: "var(--r-2) var(--r-2) 0 0",
            }}
          >
            <Icon size={14} aria-hidden="true" />
            {t(`detail.tabs.${id}`)}
            <span className="chip subtle" style={{ marginLeft: 2 }}>
              {t("detail.tabs.soon")}
            </span>
          </button>
        ))}
      </div>
      <div
        role="tabpanel"
        id={`${panelId}-panel`}
        aria-labelledby={`${panelId}-tab-${tab}`}
        data-testid={`org-panel-${tab}`}
      >
        {children}
      </div>

      <ConfirmByName
        isOpen={confirming}
        onClose={() => {
          setConfirming(false);
        }}
        onConfirm={onDelete}
        name={org.name}
        title={t("detail.delete.title")}
        description={
          org.project_count > 0
            ? t("detail.delete.withProjects", { count: org.project_count })
            : t("detail.delete.body")
        }
        confirmLabel={t("detail.delete.confirm")}
        pending={deleting}
        error={deleteFailure ? t(deleteKey(deleteFailure.code)) : null}
      />
    </div>
  );
};

const deleteKey = (code: string): string =>
  code === "org_not_empty"
    ? "failure.org_not_empty"
    : code === "forbidden"
      ? "failure.forbidden"
      : code === "network"
        ? "failure.network"
        : "failure.unknown";
