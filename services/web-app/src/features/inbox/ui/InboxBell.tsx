import { Bell } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router";
import { useBootstrap } from "@entities/session";
import { useInboxSummary } from "@entities/invitation";

/** Колокольчик «Входящих» в шапке (10.9): непрочитанные плюс ожидающие приглашения и передачи. */
export const InboxBell = () => {
  const { t } = useTranslation("inbox");
  const navigate = useNavigate();
  const boot = useBootstrap().data;
  const signedIn = boot?.mode === "server" && boot.user !== null;
  const summary = useInboxSummary(signedIn);
  if (!signedIn) return null;
  const count = summary.data
    ? summary.data.unread + summary.data.invitations + summary.data.transfers
    : (boot.inbox?.unread ?? 0);
  return (
    <InboxBellView
      count={count}
      label={t("bell", { count })}
      onOpen={() => {
        void navigate("/inbox");
      }}
    />
  );
};

export const InboxBellView = ({
  count,
  label,
  onOpen,
}: {
  count: number;
  label: string;
  onOpen: () => void;
}) => (
  <button
    type="button"
    className="icon-btn tt"
    data-tt={label}
    aria-label={label}
    data-testid="inbox-bell"
    data-count={count}
    onClick={onOpen}
    style={{ width: 32, height: 32, position: "relative" }}
  >
    <Bell size={16} />
    {count > 0 && (
      <span
        aria-hidden="true"
        style={{
          position: "absolute",
          top: 3,
          right: 2,
          minWidth: 15,
          height: 15,
          padding: "0 4px",
          borderRadius: 8,
          background: "var(--c-err)",
          color: "white",
          fontSize: 9.5,
          fontWeight: 600,
          lineHeight: "15px",
          textAlign: "center",
        }}
      >
        {count > 99 ? "99+" : count}
      </span>
    )}
  </button>
);
