import { useState } from "react";
import { useTranslation } from "react-i18next";
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
      <header className="flex flex-col" style={{ gap: 4 }}>
        <h1 style={{ margin: 0, fontSize: 20, fontWeight: 600 }}>
          {t("title")}
        </h1>
        <p style={{ margin: 0, fontSize: 13, color: "var(--fg-2)" }}>
          {t("lead")}
        </p>
      </header>
      <div
        role="tablist"
        aria-label={t("tabs.label")}
        className="flex"
        style={{ gap: 4, borderBottom: "1px solid var(--border)" }}
      >
        {TABS.map((id) => (
          <button
            key={id}
            type="button"
            role="tab"
            id={`users-tab-${id}`}
            aria-selected={tab === id}
            aria-controls="users-panel-current"
            data-testid={`users-tab-${id}`}
            className="row-btn"
            style={{
              width: "auto",
              padding: "8px 12px",
              gap: 6,
              borderRadius: "var(--r-2) var(--r-2) 0 0",
              borderBottom:
                tab === id
                  ? "2px solid var(--accent)"
                  : "2px solid transparent",
              fontWeight: tab === id ? 600 : 400,
            }}
            onClick={() => {
              setTab(id);
            }}
          >
            {t(`tabs.${id}`)}
            {id === "approvals" && pending > 0 && (
              <span className="chip accent" style={{ marginLeft: 2 }}>
                {pending}
              </span>
            )}
          </button>
        ))}
      </div>
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
