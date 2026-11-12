import { useTranslation } from "react-i18next";
import { clsx } from "clsx";
import { Bell, Link2 } from "lucide-react";
import type { RouteParticipant, SigningRoute } from "@entities/signing-route";
import { CopyField } from "@shared/ui";
import { formatDay, formatMoment } from "../lib/format";
import {
  hasOptionalPair,
  isLinkable,
  isRemindable,
  personMoment,
  personStateKey,
  personTone,
  remindLockedUntil,
  returnsNextRound,
  type PersonTone,
} from "../lib/routeView";
import { usePersonaLabel } from "../lib/usePersonaLabel";
import { displayName } from "../lib/useWaitText";
import { SkipAction } from "./SkipAction";

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
  /**
   * Автор управляет маршрутом: у тех, чья очередь, «Напомнить»; «Скопировать ссылку» у каждого
   * человека идущего маршрута, кто ещё не закончил.
   */
  canManage: boolean;
  /**
   * На сервере настроена почта. Тогда ссылку приглашённому несёт письмо, и копировать нечего:
   * новая ссылка сломала бы отправленную. Остаётся «Напомнить» (повтор письма).
   */
  mailEnabled: boolean;
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
  mailEnabled,
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
                const invited = person.state === "invited";
                // Без почты приглашённому напомнить нечем: «Напомнить» отдаёт ту же ссылку, что
                // и «Скопировать ссылку», и 12 часов её не закрывают. Копирование не закрыто никогда
                // и доступно не только тому, чья очередь: ссылку можно разослать заранее.
                const remindLocked =
                  lockedUntil !== null && (!invited || mailEnabled);
                // «Пропустить» только у идущего маршрута и тому, кого сервер разрешил пропустить;
                // причина отказа видна, если у человека есть необязательные подписи (13.9).
                const skipInfo = route.status === "active" ? person.skip : null;
                const canSkip = canManage && skipInfo?.available === true;
                const skipBlocker =
                  canManage &&
                  skipInfo !== null &&
                  (skipInfo.blocker === "not_turn" ||
                    skipInfo.blocker === "required_slots") &&
                  hasOptionalPair(route, person)
                    ? skipInfo.blocker
                    : null;
                const isMe = person.user_id !== null && person.user_id === meId;
                // Себе ссылку не копируют: страница подписи и так открывается кнопкой карточки.
                const canCopy =
                  canManage &&
                  !isMe &&
                  isLinkable(route, person) &&
                  !(invited && mailEnabled);
                const lockTitle =
                  lockedUntil === null
                    ? undefined
                    : t("action.remindAfter", {
                        time: formatMoment(lockedUntil),
                      });
                // Приглашённого называем по карточке проекта, маска почты только подсказка.
                const shownName = displayName({
                  ...person,
                  cardName: person.card_name,
                });
                const name =
                  shownName.name ??
                  (invited ? t("person.invitee") : t("person.nobody"));
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
                      {shownName.hint !== null && (
                        <span
                          className="dim mono"
                          style={{ fontSize: "0.6875rem" }}
                          data-testid={`signing-person-hint-${person.id}`}
                        >
                          {shownName.hint}
                        </span>
                      )}
                      {isMe && (
                        <span className="chip subtle">{t("person.you")}</span>
                      )}
                      {role !== null && <span className="dim">{role}</span>}
                      {showState && (
                        <span style={{ color: COLOR[tone] }}>
                          {moment?.kind === "skipped"
                            ? t("skip.skippedOn", {
                                date: formatDay(moment.iso),
                              })
                            : t(`person.state.${personStateKey(person)}`)}
                          {moment &&
                            moment.kind !== "skipped" &&
                            ` ${
                              moment.kind === "at"
                                ? formatDay(moment.iso)
                                : t("since", { date: formatDay(moment.iso) })
                            }`}
                        </span>
                      )}
                      {(remindable || canCopy || canSkip) && (
                        // На узком экране кнопки уходят на свою строку и не ломаются внутри.
                        <span
                          className="flex items-center"
                          style={{
                            gap: "0.25rem",
                            marginLeft: "auto",
                            flexWrap: "wrap",
                            justifyContent: "flex-end",
                          }}
                        >
                          {remindable && (
                            // Подсказка на обёртке: у погашенной кнопки нет наведения.
                            <span title={remindLocked ? lockTitle : undefined}>
                              <button
                                type="button"
                                className="btn xs ghost"
                                style={{ whiteSpace: "nowrap" }}
                                data-testid={`signing-remind-${person.id}`}
                                disabled={busy || remindLocked}
                                onClick={() => {
                                  onRemind(person);
                                }}
                              >
                                <Bell size="0.6875rem" aria-hidden="true" />
                                {t("action.remind")}
                              </button>
                            </span>
                          )}
                          {canSkip && (
                            <SkipAction route={route} person={person} />
                          )}
                          {canCopy && (
                            <button
                              type="button"
                              className="btn xs ghost"
                              style={{ whiteSpace: "nowrap" }}
                              data-testid={`signing-copy-${person.id}`}
                              disabled={busy}
                              onClick={() => {
                                onCopyLink(person);
                              }}
                            >
                              <Link2 size="0.6875rem" aria-hidden="true" />
                              {t("action.copyLink")}
                            </button>
                          )}
                        </span>
                      )}
                    </div>
                    {canSkip && (
                      <span
                        className="dim"
                        style={{ fontSize: "0.71875rem", lineHeight: 1.45 }}
                        data-testid={`signing-skip-hint-${person.id}`}
                      >
                        {t("skip.hint")}
                      </span>
                    )}
                    {skipBlocker !== null && (
                      <span
                        className="dim"
                        style={{ fontSize: "0.71875rem", lineHeight: 1.45 }}
                        data-testid={`signing-skip-blocker-${person.id}`}
                      >
                        {t(`skip.blocked.${skipBlocker}`)}
                      </span>
                    )}
                    {returnsNextRound(route, person) && (
                      <span
                        className="dim"
                        style={{ fontSize: "0.71875rem", lineHeight: 1.45 }}
                        data-testid={`signing-skip-returns-${person.id}`}
                      >
                        {t("skip.returns")}
                      </span>
                    )}
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
