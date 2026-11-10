import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router";
import { useQueryClient } from "@tanstack/react-query";
import { FileText, PenLine, Route, Send, TriangleAlert, X } from "lucide-react";
import type { z } from "zod";
import type { ProjectResponseSchema } from "@entities/project";
import { useBootstrap } from "@entities/session";
import {
  canArchiveRoute,
  canCancelRoute,
  isActionable,
  isResend,
  signingPagePath,
  signingRouteApi,
  signingRouteEditorPath,
  signingRouteKeys,
  useArchiveSigningRoute,
  useCancelSigningRoute,
  routeWaitOf,
  useRemindSigningParticipant,
  useSendSigningRoute,
  useSigningRoute,
  useSigningRoutes,
  type RouteParticipant,
  type SigningRoute,
} from "@entities/signing-route";
import { toast } from "@shared/lib";
import { Modal, Spinner } from "@shared/ui";
import { absoluteUrl, formatDay } from "../lib/format";
import {
  earliest,
  lastReturn,
  meIn,
  pickCurrentRoute,
  returnedDocId,
  signedTally,
  waitingFor,
} from "../lib/routeView";
import { useNow } from "../lib/useNow";
import { useWaitText } from "../lib/useWaitText";
import { useErrorText } from "../model/useErrorText";
import { useParticipantLink } from "../model/useParticipantLink";
import { RouteSteps } from "./RouteSteps";

type Project = z.infer<typeof ProjectResponseSchema>;

export type SigningRouteCardProps = {
  project: Project;
  profileId: string;
  /** Подписи точки из расчёта готовности: их счёт показываем, пока маршрута нет. */
  signatures: { done: number; total: number };
};

const WAITING_NAMES = 2;

const Shell = ({ children }: { children: React.ReactNode }) => {
  const { t } = useTranslation("signingProgress");
  return (
    <section
      className="card"
      data-testid="signing-card"
      style={{
        padding: "1.125rem",
        display: "flex",
        flexDirection: "column",
        gap: "0.75rem",
      }}
    >
      <h3 style={{ margin: 0, fontSize: "0.8125rem", fontWeight: 600 }}>
        {t("title")}
      </h3>
      {children}
    </section>
  );
};

const Actions = ({ children }: { children: React.ReactNode }) => (
  <div
    className="flex items-center"
    style={{ gap: "0.5rem", flexWrap: "wrap" }}
  >
    {children}
  </div>
);

/**
 * Карточка «Подписание» на точке сдачи (docs/design/signing-route.md, 3.1): маршрута нет,
 * черновик, идёт (шаг и чья очередь), остановлен (почему), возвращён (кем и с каким
 * комментарием), завершён, отменён. Действия автора: отправить или открыть маршрут, напомнить,
 * скопировать ссылку подписанту (без почты на сервере), отменить, отправить заново. Маршруты
 * есть только на сервере; локально карточки нет.
 */
export const SigningRouteCard = ({
  project,
  profileId,
  signatures,
}: SigningRouteCardProps) => {
  const { t } = useTranslation("signingProgress");
  const boot = useBootstrap().data;
  // Маршруты есть только на сервере и только вошедшему: гостю по ссылке они закрыты (раздел 7).
  const isServer = boot?.mode === "server" && boot.user !== null;
  // Управлять маршрутом может тот, у кого есть право сдачи: владелец и редактор (раздел 7).
  const canManage = project.my_role === "owner" || project.my_role === "editor";
  const list = useSigningRoutes(project.id, profileId, { enabled: isServer });
  const current = pickCurrentRoute(list.data?.items ?? []);
  const routeQuery = useSigningRoute(project.id, current?.id ?? "", {
    enabled: current !== null,
  });
  const editorPath = signingRouteEditorPath(project.id, profileId);

  // Чужой проект по ссылке и гость маршрутов не видят (404): карточку не показываем.
  if (!isServer || list.isError) return null;
  if (!list.data) return null;

  if (current === null) {
    // Без подписей точке маршрут не нужен; читателю отправлять нечего.
    if (!canManage || signatures.total === 0) return null;
    return (
      <Shell>
        <div className="flex flex-col" style={{ gap: "0.25rem" }}>
          <strong style={{ fontSize: "0.8125rem" }}>
            {t("signed", signatures)}
          </strong>
          <span className="dim" style={{ fontSize: "0.75rem" }}>
            {t("none")}
          </span>
        </div>
        <Actions>
          <Link
            to={editorPath}
            className="btn sm primary"
            data-testid="signing-send"
          >
            <Send size="0.75rem" aria-hidden="true" />
            {t("action.send")}
          </Link>
        </Actions>
      </Shell>
    );
  }

  const route = routeQuery.data;
  if (!route) {
    return (
      <Shell>
        {routeQuery.isError ? (
          <div
            className="flex items-center"
            style={{ gap: "0.5rem", fontSize: "0.75rem" }}
          >
            <span style={{ color: "var(--c-err)" }}>{t("loadFailed")}</span>
            <button
              type="button"
              className="btn xs"
              onClick={() => {
                void routeQuery.refetch();
              }}
            >
              {t("retry")}
            </button>
          </div>
        ) : (
          <div className="flex justify-center" style={{ padding: "0.5rem" }}>
            <Spinner size="sm" />
          </div>
        )}
      </Shell>
    );
  }

  return (
    <RouteBody
      key={route.id}
      route={route}
      projectId={project.id}
      editorPath={`${editorPath}?route=${encodeURIComponent(route.id)}`}
      canManage={canManage}
      meId={boot.user?.id ?? null}
      mailEnabled={boot.auth.smtp_enabled}
    />
  );
};

type RouteBodyProps = {
  route: SigningRoute;
  projectId: string;
  editorPath: string;
  canManage: boolean;
  meId: string | null;
  /** На сервере настроена почта: приглашения и напоминания уходят письмом. */
  mailEnabled: boolean;
};

const RouteBody = ({
  route,
  projectId,
  editorPath,
  canManage,
  meId,
  mailEnabled,
}: RouteBodyProps) => {
  const { t } = useTranslation("signingProgress");
  const navigate = useNavigate();
  const client = useQueryClient();
  const waitText = useWaitText();
  const errorText = useErrorText();
  const remind = useRemindSigningParticipant(projectId, route.id);
  const { pendingId, setPendingId, shown, deliver, copyLink } =
    useParticipantLink(projectId, route.id);
  const cancel = useCancelSigningRoute(projectId, route.id);
  const archive = useArchiveSigningRoute(projectId, route.id);
  const send = useSendSigningRoute(projectId, route.id);
  const [isConfirming, setIsConfirming] = useState(false);
  const [isResending, setIsResending] = useState(false);

  const people = route.steps.flat();
  const now = useNow(people.some((p) => p.reminded_at !== null));
  const waiting = waitingFor(route);
  const tally = signedTally(route);
  const me = meIn(route, meId);
  const signingPath = signingPagePath(projectId, route.id);

  const wait = routeWaitOf(route, meId);
  const who = (person: RouteParticipant): string =>
    waitText.who({ ...person, cardName: person.card_name });

  // «Напомнить»; у приглашённого это повтор приглашения, без почты сервер отдаёт ссылку (6.5).
  const requestReminder = (person: RouteParticipant) => {
    setPendingId(person.id);
    remind.mutate(person.id, {
      onSuccess: (reply) => {
        if (reply.link !== null) {
          void deliver(
            person,
            absoluteUrl(reply.link),
            t("toast.inviteCopied"),
          );
          return;
        }
        toast.success(
          person.state === "invited"
            ? t("toast.inviteResent")
            : reply.delivery === "email"
              ? t("toast.remindedEmail")
              : t("toast.remindedInbox"),
        );
      },
      onError: (error) => {
        toast.error(errorText(error));
      },
      onSettled: () => {
        setPendingId(null);
      },
    });
  };

  const onCancel = () => {
    cancel.mutate(undefined, {
      onSuccess: () => {
        toast.success(t("toast.cancelled"));
      },
      onError: (error) => {
        toast.error(errorText(error));
      },
      onSettled: () => {
        setIsConfirming(false);
      },
    });
  };

  const onArchive = () => {
    archive.mutate(undefined, {
      onSuccess: () => {
        toast.success(t("toast.archived"));
      },
      onError: (error) => {
        toast.error(errorText(error));
      },
    });
  };

  // «Отправить заново» одним нажатием: те же шаги и люди. Если что-то мешает (документ не
  // собран, человека нет в проекте), ведём в редактор маршрута, где это видно и чинится.
  const onResend = async () => {
    setIsResending(true);
    try {
      const preview = await client.fetchQuery({
        queryKey: signingRouteKeys.preview(projectId, route.id),
        queryFn: ({ signal }) =>
          signingRouteApi.preview(projectId, route.id, signal),
        staleTime: 0,
      });
      if (!preview.can_send) {
        toast.error(t("toast.blocked"));
        void navigate(editorPath);
        return;
      }
      await send.mutateAsync({
        expected: Object.fromEntries(
          preview.docs.map((doc) => [doc.doc_id, doc.token ?? ""]),
        ),
        sign: null,
      });
      toast.success(t("toast.resent"));
    } catch (error) {
      toast.error(errorText(error));
    } finally {
      setIsResending(false);
    }
  };

  const headline = ((): { text: string; tone: string } => {
    switch (route.status) {
      case "draft":
        return { text: t("draft"), tone: "var(--fg-0)" };
      case "active": {
        const step = t("step", {
          step: route.current_step ?? route.steps.length,
          total: route.steps.length,
        });
        if (waiting.length === 0) return { text: step, tone: "var(--fg-0)" };
        const names = waiting.slice(0, WAITING_NAMES).map(who).join(", ");
        const listed =
          waiting.length > WAITING_NAMES
            ? t("andMore", { names, count: waiting.length - WAITING_NAMES })
            : names;
        const since = earliest(waiting.map((p) => p.notified_at));
        const text = `${step}. ${t("waiting", { who: listed })}`;
        return {
          text:
            since === null
              ? text
              : `${text}, ${t("since", { date: formatDay(since) })}`,
          tone: "var(--fg-0)",
        };
      }
      case "paused":
        return {
          text: t(`paused.${route.stop_reason ?? "rebuilt"}`),
          tone: "var(--c-warn)",
        };
      case "returned": {
        const back = lastReturn(route);
        const name =
          back?.who ??
          people.find((p) => p.state === "returned")?.name ??
          t("someone");
        return {
          text: back?.comment
            ? t("returned", { who: name, comment: back.comment })
            : t("returnedNoComment", { who: name }),
          tone: "var(--c-warn)",
        };
      }
      case "completed":
        return { text: t("completed"), tone: "var(--c-ok)" };
      case "cancelled":
      case "archived":
        return { text: t("cancelled"), tone: "var(--fg-2)" };
    }
  })();

  const facts: string[] = [];
  if (route.status !== "draft" && tally.total + tally.optionalTotal > 0)
    facts.push(
      tally.optionalTotal > 0 ? t("signedOptional", tally) : t("signed", tally),
    );
  if (route.deadline !== null && route.status === "active") {
    const date = formatDay(route.deadline);
    facts.push(
      Date.parse(route.deadline) < now
        ? t("overdue", { date })
        : t("deadline", { date }),
    );
  }

  const docId = route.status === "returned" ? returnedDocId(route) : null;
  const busy = isResending || cancel.isPending || archive.isPending;
  const mine = me !== null && isActionable(me.next_action);
  // Отправитель ещё не подписал сам: так бывает после «Отправить на подписание» с ЭП и когда
  // подпись в «Отправить и подписать» отказала уже после отправки.
  const unsigned =
    route.status === "active" &&
    me !== null &&
    me.next_action === "sign" &&
    route.sent_by?.id === meId;
  // Почему смотрящий ждёт и когда до него дойдёт (своя очередь видна кнопкой «Перейти к подписи»).
  const myLead =
    wait !== null &&
    (wait.mine?.kind === "approved" || wait.mine?.kind === "later")
      ? waitText.lead(wait)
      : null;
  // Не принявших приглашение показываем заметно: без их согласия маршрут не сдвинется.
  const invitedLine =
    canManage && wait !== null ? waitText.invited(wait) : null;

  return (
    <Shell>
      <div
        className="flex flex-col"
        style={{ gap: "0.25rem" }}
        data-testid="signing-status"
        data-status={route.status}
        role="status"
      >
        <strong
          style={{
            fontSize: "0.8125rem",
            color: headline.tone,
            lineHeight: 1.45,
          }}
        >
          {headline.text}
        </strong>
        {facts.length > 0 && (
          <span className="dim" style={{ fontSize: "0.71875rem" }}>
            {facts.join(" · ")}
          </span>
        )}
        {unsigned && (
          <span
            className="flex items-center"
            style={{
              gap: "0.375rem",
              fontSize: "0.75rem",
              color: "var(--c-warn)",
              lineHeight: 1.45,
            }}
            data-testid="signing-unsigned"
          >
            <TriangleAlert
              size="0.8125rem"
              aria-hidden="true"
              style={{ flexShrink: 0 }}
            />
            {t("unsigned")}
          </span>
        )}
        {myLead !== null && (
          <span
            className="dim"
            style={{ fontSize: "0.75rem", lineHeight: 1.45 }}
            data-testid="signing-my-wait"
          >
            {myLead}
          </span>
        )}
        {invitedLine !== null && (
          <span
            className="flex items-start"
            style={{
              gap: "0.375rem",
              fontSize: "0.75rem",
              color: "var(--c-warn)",
              lineHeight: 1.45,
            }}
            data-testid="signing-invited"
          >
            <TriangleAlert
              size="0.8125rem"
              aria-hidden="true"
              style={{ flexShrink: 0, marginTop: "0.125rem" }}
            />
            <span>
              {invitedLine}{" "}
              {mailEnabled
                ? t("wait.invitedMail")
                : t("wait.invitedNoMailRows")}
            </span>
          </span>
        )}
      </div>

      <RouteSteps
        route={route}
        meId={meId}
        now={now}
        canManage={canManage}
        mailEnabled={mailEnabled}
        pendingId={pendingId}
        shown={shown}
        onRemind={requestReminder}
        onCopyLink={copyLink}
      />

      {(mine || canManage) && (
        <Actions>
          {mine && (
            <Link
              to={signingPath}
              className="btn sm primary"
              data-testid="signing-go"
            >
              <PenLine size="0.75rem" aria-hidden="true" />
              {t("action.sign")}
            </Link>
          )}
          {canManage && isResend(route.status) && (
            <button
              type="button"
              className={mine ? "btn sm" : "btn sm primary"}
              data-testid="signing-resend"
              disabled={busy}
              onClick={() => {
                void onResend();
              }}
            >
              {isResending ? (
                <Spinner size="sm" />
              ) : (
                <Send size="0.75rem" aria-hidden="true" />
              )}
              {t("action.resend")}
            </button>
          )}
          {canManage && docId !== null && (
            <Link
              to={`/projects/${encodeURIComponent(projectId)}/documents/${encodeURIComponent(docId)}`}
              className="btn sm"
              data-testid="signing-open-doc"
            >
              <FileText size="0.75rem" aria-hidden="true" />
              {t("action.openDoc")}
            </Link>
          )}
          {canManage && (
            <Link
              to={editorPath}
              className={
                route.status === "draft" && !mine ? "btn sm primary" : "btn sm"
              }
              data-testid="signing-open"
            >
              <Route size="0.75rem" aria-hidden="true" />
              {t("action.open")}
            </Link>
          )}
          {canManage && canArchiveRoute(route.status) && (
            <span title={t("action.archiveHint")}>
              <button
                type="button"
                className="btn sm ghost"
                data-testid="signing-archive"
                disabled={busy}
                onClick={onArchive}
              >
                {t("action.archive")}
              </button>
            </span>
          )}
          {canManage && canCancelRoute(route.status) && (
            <button
              type="button"
              className="btn sm ghost danger"
              data-testid="signing-cancel"
              disabled={busy}
              onClick={() => {
                setIsConfirming(true);
              }}
            >
              <X size="0.75rem" aria-hidden="true" />
              {t("action.cancel")}
            </button>
          )}
        </Actions>
      )}

      <Modal
        isOpen={isConfirming}
        onClose={() => {
          setIsConfirming(false);
        }}
        title={t("confirm.title")}
        description={t("confirm.text")}
        footer={
          <>
            <button
              type="button"
              className="btn"
              disabled={cancel.isPending}
              onClick={() => {
                setIsConfirming(false);
              }}
            >
              {t("confirm.keep")}
            </button>
            <button
              type="button"
              className="btn primary"
              data-testid="signing-cancel-confirm"
              disabled={cancel.isPending}
              onClick={onCancel}
            >
              {cancel.isPending && <Spinner size="sm" />}
              {t("action.cancel")}
            </button>
          </>
        }
      />
    </Shell>
  );
};
