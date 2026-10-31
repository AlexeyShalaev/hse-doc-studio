import { useState } from "react";
import { useTranslation } from "react-i18next";
import { failureCode } from "@shared/api";
import { toast } from "@shared/lib";
import { CopyField, Modal } from "@shared/ui";
import type { ProjectRole } from "@entities/session";
import {
  useDecideAccessRequest,
  useProjectAccessRequests,
  useProjectInvitations,
  useProjectTransfer,
  useResendInvitation,
  useRevokeInvitation,
} from "@entities/invitation";
import { useFailureText } from "../lib/failure";
import { ApproveDialog } from "./ApproveDialog";
import { PendingAccessView } from "./PendingAccessView";

export type PendingAccessSectionProps = {
  projectId: string;
  myRole: ProjectRole | null;
  /** Право решать доступ (владелец или редактор с правом делиться). */
  canManage?: boolean;
};

/** Слот «Ожидают» панели «Доступ»: данные, повтор, отзыв и решения по запросам. */
export const PendingAccessSection = ({
  projectId,
  myRole,
  canManage = myRole === "owner",
}: PendingAccessSectionProps) => {
  const { t, i18n } = useTranslation("invitations");
  const failureText = useFailureText();
  const invitations = useProjectInvitations(projectId, canManage);
  const requests = useProjectAccessRequests(projectId, canManage);
  const transfer = useProjectTransfer(projectId, myRole !== null);
  const resend = useResendInvitation(projectId);
  const revoke = useRevokeInvitation(projectId);
  const decide = useDecideAccessRequest(projectId);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [approving, setApproving] = useState<{
    id: string;
    name: string;
  } | null>(null);
  const [link, setLink] = useState<string | null>(null);

  const fail = (e: unknown) => {
    toast.error(failureText(failureCode(e)));
  };
  const done = () => {
    setBusyId(null);
  };

  return (
    <>
      <PendingAccessView
        invitations={canManage ? (invitations.data?.items ?? []) : []}
        requests={canManage ? (requests.data?.items ?? []) : []}
        transferPending={myRole !== "owner" && transfer.data?.pending === true}
        busyId={busyId}
        lang={i18n.language}
        onResend={(inv) => {
          setBusyId(inv.id);
          resend.mutate(inv.id, {
            onSuccess: (result) => {
              if (result.link) setLink(result.link);
              else toast.success(t("pending.resent"));
            },
            onError: fail,
            onSettled: done,
          });
        }}
        onRevoke={(inv) => {
          setBusyId(inv.id);
          revoke.mutate(inv.id, {
            onSuccess: () => {
              toast.success(t("pending.revoked"));
            },
            onError: fail,
            onSettled: done,
          });
        }}
        onApprove={(req) => {
          setApproving({ id: req.id, name: req.requester.name });
        }}
        onDeny={(req) => {
          setBusyId(req.id);
          decide.mutate(
            { requestId: req.id, approve: null },
            {
              onSuccess: () => {
                toast.success(
                  t("requests.denied", { name: req.requester.name }),
                );
              },
              onError: fail,
              onSettled: done,
            },
          );
        }}
      />
      <ApproveDialog
        projectId={projectId}
        request={approving}
        onClose={() => {
          setApproving(null);
        }}
      />
      <Modal
        isOpen={link !== null}
        onClose={() => {
          setLink(null);
        }}
        title={t("form.manualTitle")}
      >
        <div data-testid="invite-link">
          <CopyField value={link ?? ""} label={t("form.linkLabel")} />
        </div>
      </Modal>
    </>
  );
};
