import { useRef, type ReactNode } from "react";
import { Lock, UserPlus } from "lucide-react";
import { useSearchParams } from "react-router";
import { useTranslation } from "react-i18next";
import { ApiError } from "@shared/api";
import { Button, EmptyState, PageHeader, PageTabs } from "@shared/ui";
import type { AdminUser } from "@entities/session";
import { useApprovals, useUsers } from "../api/adminUsersQueries";
import { ApprovalsPanel } from "./ApprovalsPanel";
import { InvitationsPanel } from "./InvitationsPanel";
import { UsersPanel } from "./UsersPanel";

export type UsersTab = "users" | "invitations" | "approvals";

const TABS: readonly UsersTab[] = ["users", "invitations", "approvals"];

const isTab = (value: string | null): value is UsersTab =>
  TABS.includes(value as UsersTab);

/** Раздел «Пользователи»: люди, приглашения и очередь одобрений. */
export const AdminUsers = ({
  initialTab = "users",
  renderOrgs,
}: {
  initialTab?: UsersTab;
  /** Организации человека в его карточке: их рисует раздел «Организации». */
  renderOrgs?: ((user: AdminUser) => ReactNode) | undefined;
}) => {
  const { t } = useTranslation("adminUsers");
  // Вкладка в адресе (?tab=…), как и поиск с фильтрами её списка: ссылка
  // открывает тот же вид. Смена вкладки сбрасывает условия прежнего списка,
  // у вкладок свои фильтры с теми же именами (status).
  const [params, setParams] = useSearchParams();
  const fromUrl = params.get("tab");
  const tab: UsersTab = isTab(fromUrl) ? fromUrl : initialTab;
  const setTab = (next: UsersTab) => {
    if (next === tab) return;
    setParams(next === "users" ? {} : { tab: next });
  };
  // Те же ключи, что у первой страницы вкладок: лишних запросов нет.
  const list = useUsers({ q: "", status: "", page: 0 });
  const people = list.data?.total;
  // Не админу установки сервер отвечает так, будто раздела нет.
  const forbidden =
    list.error instanceof ApiError &&
    (list.error.status === 403 || list.error.status === 404);
  const pending = useApprovals(0).data?.total ?? 0;
  const emailRef = useRef<HTMLInputElement>(null);
  const count = (id: UsersTab) => {
    if (id === "users" && people !== undefined) return { count: people };
    if (id === "approvals" && pending > 0)
      return { count: pending, countTone: "accent" as const };
    return {};
  };

  if (forbidden) {
    return (
      <div className="ppl-page" data-testid="admin-users">
        <PageHeader title={t("title")} description={t("lead")} />
        <EmptyState
          framed
          testId="users-forbidden"
          icon={<Lock size={18} />}
          title={t("forbidden.title")}
          description={t("forbidden.body")}
        />
      </div>
    );
  }

  return (
    <div className="ppl-page" data-testid="admin-users">
      <PageHeader
        title={t("title")}
        description={t("lead")}
        actions={
          // Действие на всех вкладках одно: на вкладке приглашений кнопка
          // просто ставит курсор в поле почты.
          <Button
            size="sm"
            type="button"
            data-testid="users-invite"
            onClick={() => {
              setTab("invitations");
              // Вкладка отрисуется в этом же кадре: фокус в поле почты после неё.
              requestAnimationFrame(() => {
                emailRef.current?.focus();
              });
            }}
          >
            <UserPlus size={14} aria-hidden="true" />
            {t("invite")}
          </Button>
        }
        tabs={
          <PageTabs
            label={t("tabs.label")}
            value={tab}
            onChange={setTab}
            idPrefix="users-tab"
            panelId="users-panel-current"
            tabs={TABS.map((id) => ({
              id,
              label: t(`tabs.${id}`),
              testId: `users-tab-${id}`,
              ...count(id),
            }))}
          />
        }
      />
      <div
        role="tabpanel"
        id="users-panel-current"
        aria-labelledby={`users-tab-${tab}`}
      >
        {tab === "users" && <UsersPanel renderOrgs={renderOrgs} />}
        {tab === "invitations" && <InvitationsPanel ref={emailRef} />}
        {tab === "approvals" && <ApprovalsPanel />}
      </div>
    </div>
  );
};
