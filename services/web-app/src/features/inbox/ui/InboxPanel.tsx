import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { useNavigate, useSearchParams } from "react-router";
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
  type MyInvitation,
  type Notification,
} from "@entities/invitation";
import {
  accountSigningApi,
  signingPagePath,
  signingRouteKeys,
  useMySigningTasks,
  type SigningTaskSummary,
} from "@entities/signing-route";
import {
  ApproveDialog,
  useInvitationFailureText,
} from "@features/project-invitations";
import { notificationRoute } from "../lib/notificationTarget";
import { inboxTabOf, type InboxTab } from "../lib/inboxTab";
import { sortSigningTasks } from "../lib/signingTasks";
import { InboxView } from "./InboxView";

/** Данные и действия «Входящих». Открытие страницы ничего не отмечает прочитанным. */
export const InboxPanel = () => {
  const { t, i18n } = useTranslation("inbox");
  const navigate = useNavigate();
  const client = useQueryClient();
  const failureText = useInvitationFailureText();
  // Вкладка в адресе: колокольчик ведёт прямо в «На подпись» (`/inbox?tab=signing`).
  const [params, setParams] = useSearchParams();
  const tab = inboxTabOf(params.get("tab"));
  const setTab = (next: InboxTab) => {
    setParams(next === "all" ? {} : { tab: next }, { replace: true });
  };
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
  const signingTasks = useMySigningTasks();
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

  /**
   * Куда вести после «Принять». Приглашение подписанта маршрута: принятие уже поставило его в
   * маршрут (docs/design/signing-route.md, 6.5 и 6.6), и если сейчас его очередь, задача есть в
   * «На подпись». Тогда сразу на страницу подписи, как ссылка приглашения с `?next=`. Иначе в
   * проект, как раньше: очередь не дошла, и о ней придёт уведомление.
   */
  const openAccepted = async (inv: MyInvitation) => {
    let task: SigningTaskSummary | undefined;
    try {
      const tasks = await client.fetchQuery({
        queryKey: signingRouteKeys.myTasks(),
        queryFn: ({ signal }) => accountSigningApi.tasks(signal),
        staleTime: 0,
      });
      task = sortSigningTasks(
        tasks.items.filter((item) => item.project.id === inv.project.id),
      )[0];
    } catch {
      // Задачи не прочитались: принятие уже состоялось, ведём в проект.
    }
    if (task) {
      toast.success(
        t("invitation.acceptedSign", { project: inv.project.name }),
      );
      void navigate(signingPagePath(task.project.id, task.route_id));
      return;
    }
    toast.success(t("invitation.accepted", { project: inv.project.name }));
    void navigate(`/projects/${inv.project.id}`);
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
        signingTasks={signingTasks.data?.items ?? []}
        signingStatus={
          signingTasks.data
            ? "ready"
            : signingTasks.isError
              ? "error"
              : "loading"
        }
        busyId={busyId}
        lang={i18n.language}
        onInvitation={(inv, accept) => {
          setBusyId(inv.id);
          decideInvitation.mutate(
            { id: inv.id, accept },
            {
              onSuccess: () => {
                if (accept) {
                  void openAccepted(inv);
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
          const route = notificationRoute(n);
          if (route) void navigate(route);
        }}
        onMarkAll={() => {
          markRead.mutate(null);
        }}
        onCancelRequest={(r) => {
          setBusyId(r.id);
          cancel.mutate(r.id, { onError: fail, onSettled: settled });
        }}
        onSigningTask={(task) => {
          void navigate(signingPagePath(task.project.id, task.route_id));
        }}
        onSigningRetry={() => {
          void signingTasks.refetch();
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
