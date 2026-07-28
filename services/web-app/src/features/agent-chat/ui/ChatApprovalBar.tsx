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
        gap: 8,
        padding: 10,
        borderTop: "1px solid var(--c-warn)",
        background: "var(--bg-1)",
      }}
    >
      <div
        className="flex items-center"
        style={{ gap: 6, fontSize: 12, color: "var(--c-warn)" }}
      >
        <ShieldAlert size={13} />
        {t("approval.prompt")}
      </div>
      {approvals.map((approval) => (
        <div
          key={approval.callId}
          className="mono"
          style={{
            fontSize: 11,
            color: "var(--fg-2)",
            padding: "4px 8px",
            borderRadius: 4,
            background: "var(--bg-2)",
          }}
        >
          {approval.name}
          <span className="dim"> ({JSON.stringify(approval.args)})</span>
        </div>
      ))}
      <div className="flex items-center" style={{ gap: 6 }}>
        <button
          type="button"
          className="btn xs"
          disabled={pending}
          onClick={() => {
            onApprove(approvals.map((a) => a.callId));
          }}
        >
          <Check size={11} />
          {t("approval.apply")}
        </button>
        <button
          type="button"
          className="btn xs"
          disabled={pending}
          onClick={onReject}
        >
          <X size={11} />
          {t("approval.reject")}
        </button>
      </div>
    </div>
  );
};
