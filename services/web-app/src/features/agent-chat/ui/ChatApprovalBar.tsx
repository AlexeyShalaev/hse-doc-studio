import { Check, ShieldAlert, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { PendingApproval } from "../lib/useAgentRunStream";

type ChatApprovalBarProps = {
  approvals: PendingApproval[];
  pending: boolean;
  onApprove: (callIds: string[]) => void;
  onReject: () => void;
};

export const ChatApprovalBar = ({
  approvals,
  pending,
  onApprove,
  onReject,
}: ChatApprovalBarProps) => {
  const { t } = useTranslation("agentChat");
  if (approvals.length === 0) return null;
  return (
    <div
      className="flex flex-col"
      style={{
        gap: "0.5rem",
        padding: "0.625rem",
        borderTop: "1px solid var(--c-warn)",
        background: "var(--bg-1)",
      }}
    >
      <div
        className="flex items-center"
        style={{ gap: "0.375rem", fontSize: "0.75rem", color: "var(--c-warn)" }}
      >
        <ShieldAlert size="0.8125rem" />
        {t("approval.prompt")}
      </div>
      {approvals.map((approval) => (
        <div
          key={approval.callId}
          className="mono"
          style={{
            fontSize: "0.6875rem",
            color: "var(--fg-2)",
            padding: "0.25rem 0.5rem",
            borderRadius: "0.25rem",
            background: "var(--bg-2)",
          }}
        >
          {approval.name}
          <span className="dim"> ({JSON.stringify(approval.args)})</span>
        </div>
      ))}
      <div className="flex items-center" style={{ gap: "0.375rem" }}>
        <button
          type="button"
          className="btn xs"
          disabled={pending}
          onClick={() => {
            onApprove(approvals.map((a) => a.callId));
          }}
        >
          <Check size="0.6875rem" />
          {t("approval.apply")}
        </button>
        <button
          type="button"
          className="btn xs"
          disabled={pending}
          onClick={onReject}
        >
          <X size="0.6875rem" />
          {t("approval.reject")}
        </button>
      </div>
    </div>
  );
};
