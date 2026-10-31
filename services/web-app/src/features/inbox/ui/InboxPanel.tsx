import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router";
import { failureCode } from "@shared/api";
import { toast } from "@shared/lib";
import {
  projectInvitationsApi,
  useCancelAccessRequest,
  useDecideInvitation,
  useDecideTransfer,
  useMarkNotificationsRead,
  useMyAccessRequests,
  useMyInvitations,
  useMyTransfers,
  useNotifications,
  type Notification,
} from "@entities/invitation";
import {
  ApproveDialog,
  useInvitationFailureText,
} from "@features/project-invitations";
import { InboxView, type InboxTab } from "./InboxView";

/** Данные и действия «Входящих». Открытие страницы ничего не отмечает прочитанным. */
export const InboxPanel = () => {
  const { t, i18n } = useTranslation("inbox");
  const navigate = useNavigate();
  const failureText = useInvitationFailureText();
  const [tab, setTab] = useState<InboxTab>("all");
  const [busyId, setBusyId] = useState<string | null>(null);
  const [approving, setApproving] = useState<{
    projectId: string;
    id: string;
    name: string;
    notificationId: string;
  } | null>(null);
  const invitations = useMyInvitations();
  const transfers = useMyTransfers();
  const notifications = useNotifications();
  const myRequests = useMyAccessRequests();
  const decideInvitation = useDecideInvitation();
  const decideTransfer = useDecideTransfer();
  const markRead = useMarkNotificationsRead();
  const cancel = useCancelAccessRequest();
  const fail = (e: unknown) => {
    toast.error(failureText(failureCode(e)));
  };
  const settled = () => {
    setBusyId(null);
  };

  const denyRequest = (n: Notification) => {
    if (!n.payload.project_id || !n.payload.ref_id) return;
    setBusyId(n.id);
    projectInvitationsApi
      .deny(n.payload.project_id, n.payload.ref_id)
      .then(() => {
        toast.success(t("request.denied"));
      })
      .catch(fail)
      .finally(() => {
        markRead.mutate([n.id]);
        settled();
      });
  };

  return (
    <>
      <InboxView
        tab={tab}
        onTab={setTab}
        invitations={invitations.data ?? []}
        transfers={transfers.data ?? []}
        notifications={notifications.data?.items ?? []}
        myRequests={myRequests.data ?? []}
        busyId={busyId}
        lang={i18n.language}
        onInvitation={(inv, accept) => {
          setBusyId(inv.id);
          decideInvitation.mutate(
            { id: inv.id, accept },
            {
              onSuccess: () => {
                if (accept) {
                  toast.success(
                    t("invitation.accepted", { project: inv.project.name }),
                  );
                  void navigate(`/projects/${inv.project.id}`);
                } else {
                  toast.info(t("invitation.declined"));
                }
              },
              onError: fail,
              onSettled: settled,
            },
          );
        }}
        onTransfer={(tr, accept) => {
          if (accept && !window.confirm(t("transfer.confirm"))) return;
          setBusyId(tr.id);
          decideTransfer.mutate(
            { id: tr.id, accept },
            {
              onSuccess: () => {
                toast.success(
                  accept
                    ? t("transfer.accepted", { project: tr.project.name })
                    : t("transfer.declined"),
                );
              },
              onError: fail,
              onSettled: settled,
            },
          );
        }}
        onRequestDecision={(n, approve) => {
          if (!n.payload.project_id || !n.payload.ref_id) return;
          if (approve) {
            setApproving({
              projectId: n.payload.project_id,
              id: n.payload.ref_id,
              name: n.payload.actor_name ?? "",
              notificationId: n.id,
            });
          } else {
            denyRequest(n);
          }
        }}
        onNotification={(n) => {
          if (n.read_at === null) markRead.mutate([n.id]);
          if (n.payload.project_id && n.kind !== "member_removed") {
            void navigate(`/projects/${n.payload.project_id}`);
          }
        }}
        onMarkAll={() => {
          markRead.mutate(null);
        }}
        onCancelRequest={(r) => {
          setBusyId(r.id);
          cancel.mutate(r.id, { onError: fail, onSettled: settled });
        }}
      />
      {approving && (
        <ApproveDialog
          projectId={approving.projectId}
          request={{ id: approving.id, name: approving.name }}
          onClose={() => {
            markRead.mutate([approving.notificationId]);
            setApproving(null);
          }}
        />
      )}
    </>
  );
};
