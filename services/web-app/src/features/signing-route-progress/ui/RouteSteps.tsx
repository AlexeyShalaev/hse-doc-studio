import { useTranslation } from "react-i18next";
import { clsx } from "clsx";
import { Bell, Link2 } from "lucide-react";
import type { RouteParticipant, SigningRoute } from "@entities/signing-route";
import { CopyField } from "@shared/ui";
import { formatDay, formatMoment } from "../lib/format";
import {
  isRemindable,
  personMoment,
  personStateKey,
  personTone,
  remindLockedUntil,
  type PersonTone,
} from "../lib/routeView";
import { usePersonaLabel } from "../lib/usePersonaLabel";

const DOT: Record<PersonTone, string> = {
  ok: "ok",
  now: "info",
  warn: "warn",
  idle: "pending",
};

const COLOR: Record<PersonTone, string> = {
  ok: "var(--c-ok)",
  now: "var(--c-info)",
  warn: "var(--c-warn)",
  idle: "var(--fg-3)",
};

export type RouteStepsProps = {
  route: SigningRoute;
  meId: string | null;
  now: number;
  /** Автор управляет маршрутом: у тех, чья очередь, «Напомнить» и «Скопировать ссылку». */
  canManage: boolean;
  /** Чьё напоминание или ссылка сейчас запрашиваются. */
  pendingId: string | null;
  /** Ссылка, которую не удалось положить в буфер: показываем её под человеком. */
  shown: { participantId: string; url: string } | null;
  onRemind: (person: RouteParticipant) => void;
  onCopyLink: (person: RouteParticipant) => void;
};

/** Ход маршрута по шагам: кто, в какой роли, что сделал или что от него ждут, с какого числа. */
export const RouteSteps = ({
  route,
  meId,
  now,
  canManage,
  pendingId,
  shown,
  onRemind,
  onCopyLink,
}: RouteStepsProps) => {
  const { t } = useTranslation("signingProgress");
  const personaLabel = usePersonaLabel();
  // До отправки состояний ещё нет: черновик показывает только порядок.
  const showState = route.status !== "draft";

  return (
    <ol
      aria-label={t("title")}
      style={{
        listStyle: "none",
        margin: 0,
        padding: 0,
        display: "flex",
        flexDirection: "column",
        gap: "0.5rem",
      }}
    >
      {route.steps.map((step, index) => {
        const n = index + 1;
        const isCurrent = route.status === "active" && route.current_step === n;
        return (
          <li
            key={n}
            data-testid={`signing-step-${String(n)}`}
            data-current={isCurrent}
            style={{
              display: "grid",
              gridTemplateColumns: "1.25rem minmax(0, 1fr)",
              gap: "0.5rem",
              alignItems: "start",
            }}
          >
            <span
              aria-hidden="true"
              className="mono"
              style={{
                width: "1.25rem",
                height: "1.25rem",
                borderRadius: "50%",
                display: "inline-flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: "0.65625rem",
                background: isCurrent ? "var(--accent-soft)" : "var(--bg-2)",
                color: isCurrent ? "var(--accent)" : "var(--fg-2)",
                border: "1px solid var(--border)",
              }}
            >
              {n}
            </span>
            <div className="flex flex-col" style={{ gap: "0.375rem" }}>
              {step.map((person) => {
                const tone = personTone(person);
                const moment = personMoment(person);
                const role = personaLabel(person.persona);
                const remindable = canManage && isRemindable(route, person);
                const lockedUntil = remindLockedUntil(person, now);
                const busy = pendingId === person.id;
                // Приглашённому ссылку даёт повтор приглашения: он тоже раз в 12 часов.
                const copyLocked =
                  person.state === "invited" && lockedUntil !== null;
                const lockTitle =
                  lockedUntil === null
                    ? undefined
                    : t("action.remindAfter", {
                        time: formatMoment(lockedUntil),
                      });
                const name = person.name ?? t("person.nobody");
                return (
                  <div
                    key={person.id}
                    className="flex flex-col"
                    style={{ gap: "0.375rem" }}
                  >
                    <div
                      data-testid={`signing-person-${person.id}`}
                      data-state={person.state}
                      className="flex items-center"
                      style={{
                        gap: "0.25rem 0.5rem",
                        flexWrap: "wrap",
                        fontSize: "0.75rem",
                        minHeight: "1.375rem",
                      }}
                    >
                      <span
                        className={clsx(
                          "dot",
                          showState ? DOT[tone] : "pending",
                        )}
                      />
                      <span style={{ color: "var(--fg-0)", fontWeight: 500 }}>
                        {name}
                      </span>
                      {person.user_id !== null && person.user_id === meId && (
                        <span className="chip subtle">{t("person.you")}</span>
                      )}
                      {role !== null && <span className="dim">{role}</span>}
                      {showState && (
                        <span style={{ color: COLOR[tone] }}>
                          {t(`person.state.${personStateKey(person)}`)}
                          {moment &&
                            ` ${
                              moment.kind === "at"
                                ? formatDay(moment.iso)
                                : t("since", { date: formatDay(moment.iso) })
                            }`}
                        </span>
                      )}
                      {remindable && (
                        <span
                          className="flex items-center"
                          style={{ gap: "0.25rem", marginLeft: "auto" }}
                        >
                          {/* Подсказка на обёртке: у погашенной кнопки нет наведения. */}
                          <span title={lockTitle}>
                            <button
                              type="button"
                              className="btn xs ghost"
                              data-testid={`signing-remind-${person.id}`}
                              disabled={busy || lockedUntil !== null}
                              onClick={() => {
                                onRemind(person);
                              }}
                            >
                              <Bell size="0.6875rem" aria-hidden="true" />
                              {t("action.remind")}
                            </button>
                          </span>
                          <span title={copyLocked ? lockTitle : undefined}>
                            <button
                              type="button"
                              className="btn xs ghost"
                              data-testid={`signing-copy-${person.id}`}
                              disabled={busy || copyLocked}
                              onClick={() => {
                                onCopyLink(person);
                              }}
                            >
                              <Link2 size="0.6875rem" aria-hidden="true" />
                              {t("action.copyLink")}
                            </button>
                          </span>
                        </span>
                      )}
                    </div>
                    {shown?.participantId === person.id && (
                      <CopyField
                        value={shown.url}
                        label={t("linkLabel", { who: name })}
                      />
                    )}
                  </div>
                );
              })}
            </div>
          </li>
        );
      })}
    </ol>
  );
};
