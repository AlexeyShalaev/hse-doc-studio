import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import {
  CircleCheck,
  CircleDot,
  Clock,
  OctagonX,
  PenLine,
  Undo2,
} from "lucide-react";
import {
  taskWaitOf,
  type RouteSignMethod,
  type SigningTask,
} from "@entities/signing-route";
import { useWaitText } from "@features/signing-route-progress";
import { endSentence } from "@shared/lib";
import {
  actionDocs,
  type SigningPerson,
  type SigningStatus,
} from "../lib/signingState";

type Tone = "turn" | "ok" | "warn" | "idle";

/** Подпись тона и значок по состоянию. */
const look = (status: SigningStatus): { tone: Tone; icon: ReactNode } => {
  const size = "1rem";
  switch (status.kind) {
    case "turn":
      return { tone: "turn", icon: <PenLine size={size} aria-hidden /> };
    case "done":
    case "approved":
    case "completed":
      return { tone: "ok", icon: <CircleCheck size={size} aria-hidden /> };
    case "returned":
      return { tone: "warn", icon: <Undo2 size={size} aria-hidden /> };
    case "paused":
      return { tone: "warn", icon: <CircleDot size={size} aria-hidden /> };
    case "cancelled":
    case "closed":
      return { tone: "idle", icon: <OctagonX size={size} aria-hidden /> };
    case "not_yet":
    case "draft":
      return { tone: "idle", icon: <Clock size={size} aria-hidden /> };
  }
};

/** «Подписать 2 документа: картинкой или открепленной ЭП» (раздел 3.2, «Что нужно от вас»). */
const useNeedLine = (task: SigningTask, status: SigningStatus) => {
  const { t } = useTranslation("signing");
  if (status.kind !== "turn") return null;
  // Документы без изменений в новой версии (без отпечатка) не считаются: по ним делать нечего.
  const count = actionDocs(task).length || task.docs.length;
  const need = t(`need.${status.action}`, { count });
  const methods: RouteSignMethod[] =
    task.me.methods.length > 0
      ? task.me.methods
      : task.me.method
        ? [task.me.method]
        : [];
  if (count === 0 || methods.length === 0) return need;
  return t("need.withMethods", {
    need,
    methods: methods.map((m) => t(`need.via.${m}`)).join(` ${t("need.or")} `),
  });
};

const names = (people: SigningPerson[]): string =>
  people
    .map((p) => p.name)
    .filter((n): n is string => Boolean(n))
    .join(", ");

/** Главное на странице: что сейчас с маршрутом и что нужно от человека. */
export const StatusCard = ({
  task,
  status,
}: {
  task: SigningTask;
  status: SigningStatus;
}) => {
  const { t } = useTranslation("signing");
  const need = useNeedLine(task, status);
  const { tone, icon } = look(status);
  // Почему ждём и кого: согласие идёт по шагам, ЭП после фиксации PDF (раздел 4.2).
  const waitText = useWaitText();
  const wait = taskWaitOf(task);
  const lead = wait ? waitText.lead(wait) : null;
  const waitingNow = wait ? waitText.now(wait) : null;

  const body = ((): { title: string; lines: string[] } => {
    switch (status.kind) {
      case "turn":
        return {
          title: t(`status.turn.${status.action}`),
          lines: [
            ...(status.resent ? [t("status.resent")] : []),
            ...(need ? [need] : []),
          ],
        };
      case "not_yet": {
        if (lead !== null)
          return {
            title: t("status.notYetTitle"),
            lines: [
              lead,
              ...(waitingNow ? [waitingNow] : []),
              t("status.notYetLater"),
            ],
          };
        // Имя с инициалами («Петров П. П.») само кончается точкой: вторую не ставим.
        const now = names(status.now);
        return {
          title: t("status.notYetTitle"),
          lines: [
            ...(now
              ? [endSentence(t("signingProgress:wait.now", { who: now }))]
              : []),
            t("status.notYetLater"),
          ],
        };
      }
      case "approved":
        return {
          title: t("status.approvedTitle"),
          lines:
            lead !== null
              ? [lead, ...(waitingNow ? [waitingNow] : [])]
              : [t("status.approvedBody")],
        };
      case "done": {
        const next = names(status.next);
        return {
          title: t("status.doneTitle"),
          lines: [
            next
              ? endSentence(
                  t("status.doneNext", {
                    names: next,
                    count: status.next.length,
                  }),
                )
              : t("status.doneWait"),
          ],
        };
      }
      case "completed":
        return {
          title: t("status.completedTitle"),
          lines: [t("status.completedBody")],
        };
      case "returned":
        return {
          title: t(
            status.byMe ? "status.returnedMine" : "status.returnedOther",
          ),
          lines: [
            ...(status.comment
              ? [
                  t("status.returnedComment", {
                    who: status.who ?? t("history.server"),
                    comment: status.comment,
                  }),
                ]
              : []),
            t("status.returnedBody"),
          ],
        };
      case "paused":
        return {
          title: t("status.pausedTitle"),
          lines: [t(`status.paused.${status.reason ?? "unknown"}`)],
        };
      case "cancelled":
        return {
          title: t("status.cancelledTitle"),
          lines: [t("status.nothingToDo")],
        };
      case "closed":
        return {
          title: t("status.closedTitle"),
          lines: [t("status.nothingToDo")],
        };
      case "draft":
        return {
          title: t("status.draftTitle"),
          lines: [t("status.draftBody")],
        };
    }
  })();

  return (
    <section
      className="sgn-status"
      data-tone={tone}
      data-kind={status.kind}
      data-testid="signing-status"
      role="status"
    >
      <h2>
        {icon}
        {body.title}
      </h2>
      {body.lines.map((line) => (
        <p key={line}>{line}</p>
      ))}
    </section>
  );
};
