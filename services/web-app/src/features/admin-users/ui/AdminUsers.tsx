import { useState } from "react";
import { useTranslation } from "react-i18next";
import { PageHeader, PageTabs } from "@shared/ui";
import { useApprovals } from "../api/adminUsersQueries";
import { ApprovalsPanel } from "./ApprovalsPanel";
import { InvitationsPanel } from "./InvitationsPanel";
import { UsersPanel } from "./UsersPanel";

export type UsersTab = "users" | "invitations" | "approvals";

const TABS: readonly UsersTab[] = ["users", "invitations", "approvals"];

/** Раздел «Пользователи»: люди, приглашения и очередь одобрений. */
export const AdminUsers = ({
  initialTab = "users",
}: {
  initialTab?: UsersTab;
}) => {
  const { t } = useTranslation("adminUsers");
  const [tab, setTab] = useState<UsersTab>(initialTab);
  const pending = useApprovals(0).data?.total ?? 0;

  return (
    <div
      className="flex flex-col"
      style={{ gap: 14 }}
      data-testid="admin-users"
    >
      <PageHeader
        title={t("title")}
        description={t("lead")}
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
              ...(id === "approvals" && pending > 0
                ? { count: pending, countTone: "accent" as const }
                : {}),
            }))}
          />
        }
      />
      <div
        role="tabpanel"
        id="users-panel-current"
        aria-labelledby={`users-tab-${tab}`}
      >
        {tab === "users" && <UsersPanel />}
        {tab === "invitations" && <InvitationsPanel />}
        {tab === "approvals" && <ApprovalsPanel />}
      </div>
    </div>
  );
};
