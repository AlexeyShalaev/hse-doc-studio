import { useState, type ReactNode } from "react";
import { ArrowLeft, SearchX, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  Button,
  ConfirmByName,
  CopyField,
  EmptyState,
  ErrorState,
  PageHeader,
  PageTabs,
  Section,
  SettingRow,
  TableSkeleton,
  Tooltip,
} from "@shared/ui";
import type { AdminOrg } from "@entities/session";
import type { Failure } from "../lib/failure";
import { OrgMark, RoleBadge } from "./parts";

export type OrgTab = "members" | "groups" | "settings";

// Проектов во вкладках нет: списка проектов организации в API нет, их число
// стоит в шапке, а сами проекты открываются в Studio.
const TABS: readonly OrgTab[] = ["members", "groups", "settings"];

export type OrgDetailViewProps = {
  status: "loading" | "error" | "missing" | "ready";
  org: AdminOrg | null;
  tab: OrgTab;
  onTab: (tab: OrgTab) => void;
  onBack: () => void;
  onRetry?: () => void;
  /** Сколько групп: число на вкладке, пока не загрузилось, его нет. */
  groupCount?: number | null;
  /** Только админ установки удаляет организацию. */
  canDelete: boolean;
  deleting?: boolean;
  deleteFailure?: Failure | null;
  onDelete: () => void;
  onDeleteReset?: () => void;
  /** Содержимое вкладок участников и групп. */
  children?: ReactNode;
};

/** Страница организации: шапка с числами, вкладки «Участники», «Группы», «Настройки». */
export const OrgDetailView = ({
  status,
  org,
  tab,
  onTab,
  onBack,
  onRetry,
  groupCount = null,
  canDelete,
  deleting = false,
  deleteFailure = null,
  onDelete,
  onDeleteReset,
  children,
}: OrgDetailViewProps) => {
  const { t } = useTranslation("adminOrgs");
  const [confirming, setConfirming] = useState(false);

  const back = (
    <button
      type="button"
      className="org-back"
      onClick={onBack}
      data-testid="org-back"
    >
      <ArrowLeft size={14} aria-hidden="true" />
      {t("detail.back")}
    </button>
  );

  if (status === "loading") {
    return (
      <div className="org-page" role="status" aria-label={t("loading")}>
        {back}
        <div className="flex items-center" style={{ gap: 12 }}>
          <span className="adm-skel" style={{ width: 34, height: 34 }} />
          <div className="flex flex-col" style={{ gap: 8, flex: 1 }}>
            <span className="adm-skel" style={{ width: 220, height: 14 }} />
            <span className="adm-skel" style={{ width: 160 }} />
          </div>
        </div>
        <TableSkeleton rows={4} columns={3} withAvatar />
      </div>
    );
  }
  if (status === "error") {
    return (
      <div className="org-page">
        {back}
        <ErrorState framed title={t("detail.loadFailed")} onRetry={onRetry} />
      </div>
    );
  }
  if (status === "missing" || !org) {
    return (
      <div className="org-page">
        {back}
        <EmptyState
          framed
          testId="org-missing"
          icon={<SearchX size={18} />}
          title={t("detail.missing.title")}
          description={t("detail.missing.body")}
          action={
            <Button size="sm" variant="outline" type="button" onClick={onBack}>
              {t("detail.missing.action")}
            </Button>
          }
        />
      </div>
    );
  }

  const count = (id: OrgTab): number | undefined => {
    if (id === "members") return org.member_count;
    if (id === "groups") return groupCount ?? undefined;
    return undefined;
  };

  return (
    <div className="org-page" data-testid="org-detail">
      <PageHeader
        back={back}
        title={
          <span className="org-title">
            <OrgMark name={org.name} slug={org.slug} size={34} />
            <span>{org.name}</span>
          </span>
        }
        meta={
          <span className="org-meta" data-testid="org-meta">
            <span className="org-slug">{org.slug}</span>
            <span className="adm-dotsep" />
            <span>
              {t("detail.members.count", { count: org.member_count })}
            </span>
            <span className="adm-dotsep" />
            <Tooltip content={t("detail.projects.hint")}>
              <span tabIndex={0} data-testid="org-projects">
                {org.project_count > 0
                  ? t("detail.projects.count", { count: org.project_count })
                  : t("detail.projects.none")}
              </span>
            </Tooltip>
            {org.my_role && (
              <>
                <span className="adm-dotsep" />
                {/* Роль того, кто смотрит, а не состояние организации. */}
                <span data-testid="org-my-role">
                  {t("detail.myRole", {
                    role: t(`role.${org.my_role}`).toLowerCase(),
                  })}
                </span>
              </>
            )}
          </span>
        }
        tabs={
          <PageTabs
            label={t("detail.tabs.label")}
            value={tab}
            onChange={onTab}
            idPrefix="org-tab"
            panelId="org-panel"
            tabs={TABS.map((id) => {
              const n = count(id);
              return {
                id,
                label: t(`detail.tabs.${id}`),
                testId: `org-tab-${id}`,
                ...(n !== undefined ? { count: n } : {}),
              };
            })}
          />
        }
      />
      <div
        role="tabpanel"
        id="org-panel"
        aria-labelledby={`org-tab-${tab}`}
        data-testid={`org-panel-${tab}`}
      >
        {tab === "settings" && (
          <div className="org-stack org-settings" data-testid="org-settings">
            <Section
              title={t("detail.settings.title")}
              description={t("detail.settings.lead")}
            >
              <SettingRow label={t("detail.settings.name")}>
                <span style={{ fontSize: 13, color: "var(--fg-0)" }}>
                  {org.name}
                </span>
              </SettingRow>
              <SettingRow
                label={t("detail.settings.slug")}
                hint={t("detail.settings.slugHint")}
                align="stretch"
              >
                <CopyField value={org.slug} label={t("detail.settings.slug")} />
              </SettingRow>
              {org.my_role && (
                <SettingRow label={t("detail.settings.role")}>
                  <RoleBadge role={org.my_role} />
                </SettingRow>
              )}
            </Section>
            {canDelete && (
              <Section
                title={t("detail.delete.section")}
                testId="org-danger"
                className="org-danger"
              >
                <SettingRow
                  label={t("detail.delete.button")}
                  hint={
                    org.project_count > 0
                      ? t("detail.delete.hintProjects", {
                          count: org.project_count,
                        })
                      : t("detail.delete.hint")
                  }
                >
                  {org.project_count > 0 ? (
                    // Сервер всё равно откажет: кнопка выключена, подсказка
                    // объясняет почему.
                    <Tooltip content={t("detail.delete.blocked")}>
                      <span tabIndex={0} style={{ display: "inline-flex" }}>
                        <Button
                          variant="danger"
                          size="sm"
                          type="button"
                          disabled
                          data-testid="org-delete"
                          style={{ pointerEvents: "none" }}
                        >
                          <Trash2 size={14} aria-hidden="true" />
                          {t("detail.delete.button")}
                        </Button>
                      </span>
                    </Tooltip>
                  ) : (
                    <Button
                      variant="danger"
                      size="sm"
                      type="button"
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
                </SettingRow>
              </Section>
            )}
          </div>
        )}
        {(tab === "members" || tab === "groups") && children}
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
  code === "org_has_projects"
    ? "failure.org_has_projects"
    : code === "forbidden"
      ? "failure.forbidden"
      : code === "network"
        ? "failure.network"
        : "failure.unknown";
