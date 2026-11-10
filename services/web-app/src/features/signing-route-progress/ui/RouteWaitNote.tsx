import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { Link2, PenLine, TriangleAlert } from "lucide-react";
import { useProject } from "@entities/project";
import { useBootstrap } from "@entities/session";
import {
  routeWaitOf,
  signingPagePath,
  useSigningRoute,
  type RouteWait,
} from "@entities/signing-route";
import { CopyField } from "@shared/ui";
import { displayName, useWaitText } from "../lib/useWaitText";
import { useParticipantLink } from "../model/useParticipantLink";

export type RouteWaitNoteProps = {
  projectId: string;
  routeId: string;
  /** Не показывать строку о своём состоянии: её уже показывает экран (страница подписанта). */
  hideLead?: boolean;
  /** Не показывать «Сейчас ждём»: экран называет очередь сам. */
  hideNow?: boolean;
};

/**
 * Почему человек ждёт по маршруту подписания и чего именно (docs/design/signing-route.md, 4.2):
 * своё состояние, кого ждём сейчас, кто не принял приглашение. Автору маршрута рядом с не
 * принявшими приглашение «Скопировать ссылку», когда сервер писем не шлёт. Своя очередь: кнопка
 * на страницу подписи. Маршрут не идёт или ещё грузится: ничего не показывает.
 */
export const RouteWaitNote = ({
  projectId,
  routeId,
  hideLead = false,
  hideNow = false,
}: RouteWaitNoteProps) => {
  const boot = useBootstrap().data;
  const { data: project } = useProject(projectId);
  const { data: route } = useSigningRoute(projectId, routeId);
  if (!route) return null;
  const wait = routeWaitOf(route, boot?.user?.id ?? null);
  if (wait === null) return null;
  return (
    <WaitBody
      projectId={projectId}
      routeId={routeId}
      wait={wait}
      canManage={project?.my_role === "owner" || project?.my_role === "editor"}
      mailEnabled={boot?.auth.smtp_enabled ?? false}
      hideLead={hideLead}
      hideNow={hideNow}
    />
  );
};

type WaitBodyProps = {
  projectId: string;
  routeId: string;
  wait: RouteWait;
  canManage: boolean;
  mailEnabled: boolean;
  hideLead: boolean;
  hideNow: boolean;
};

const WaitBody = ({
  projectId,
  routeId,
  wait,
  canManage,
  mailEnabled,
  hideLead,
  hideNow,
}: WaitBodyProps) => {
  const { t } = useTranslation("signingProgress");
  const text = useWaitText();
  const { pendingId, shown, copyLink } = useParticipantLink(projectId, routeId);
  const lead = hideLead ? null : text.lead(wait);
  const now = hideNow ? null : text.now(wait);
  const invited = text.invited(wait);
  const canCopy = canManage && !mailEnabled;
  const act = wait.mine?.kind === "act";
  if (lead === null && now === null && invited === null) return null;

  return (
    <div
      className="flex flex-col"
      style={{ gap: "0.375rem", fontSize: "0.75rem", lineHeight: 1.45 }}
      data-testid="route-wait"
      role="note"
      aria-label={t("wait.noteLabel")}
    >
      {lead !== null && (
        <span data-testid="route-wait-lead" style={{ color: "var(--fg-1)" }}>
          {lead}
        </span>
      )}
      {now !== null && (
        <span className="dim" data-testid="route-wait-now">
          {now}
        </span>
      )}
      {act && (
        <span>
          <Link
            to={signingPagePath(projectId, routeId)}
            className="btn xs primary"
            data-testid="route-wait-go"
          >
            <PenLine size="0.6875rem" aria-hidden="true" />
            {t("wait.openSigningPage")}
          </Link>
        </span>
      )}
      {invited !== null && (
        <div
          className="flex flex-col"
          style={{
            gap: "0.375rem",
            padding: "0.5rem 0.625rem",
            borderRadius: "0.375rem",
            background: "var(--c-warn-soft)",
            color: "var(--c-warn)",
          }}
          data-testid="route-wait-invited"
        >
          <span className="flex items-start" style={{ gap: "0.375rem" }}>
            <TriangleAlert
              size="0.8125rem"
              aria-hidden="true"
              style={{ flexShrink: 0, marginTop: "0.125rem" }}
            />
            <span>
              {invited}{" "}
              {!canManage
                ? t("wait.invitedOther")
                : mailEnabled
                  ? t("wait.invitedMail")
                  : t("wait.invitedNoMail")}
            </span>
          </span>
          {canCopy &&
            wait.invited.map((person) => {
              if (person.id === null) return null;
              const id = person.id;
              const { hint } = displayName(person);
              return (
                <div
                  key={id}
                  className="flex flex-col"
                  style={{ gap: "0.25rem" }}
                >
                  <span
                    className="flex items-center"
                    style={{
                      gap: "0.5rem",
                      flexWrap: "wrap",
                      color: "var(--fg-1)",
                    }}
                  >
                    <span style={{ fontWeight: 500 }}>{text.who(person)}</span>
                    {hint !== null && <span className="dim mono">{hint}</span>}
                    <button
                      type="button"
                      className="btn xs"
                      style={{ marginLeft: "auto", whiteSpace: "nowrap" }}
                      data-testid={`route-wait-copy-${id}`}
                      disabled={pendingId === id}
                      onClick={() => {
                        copyLink({ id, state: person.state });
                      }}
                    >
                      <Link2 size="0.6875rem" aria-hidden="true" />
                      {t("action.copyLink")}
                    </button>
                  </span>
                  {shown?.participantId === id && (
                    <CopyField
                      value={shown.url}
                      label={t("linkLabel", { who: text.who(person) })}
                    />
                  )}
                </div>
              );
            })}
        </div>
      )}
    </div>
  );
};
