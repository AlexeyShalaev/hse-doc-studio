import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Send } from "lucide-react";
import {
  SIGNING_TEXT_MAX,
  type SigningRoute,
  type SigningRouteBlocker,
  type SigningRoutePreview,
} from "@entities/signing-route";
import { pickLocalized } from "@shared/lib";
import { Notice, Spinner } from "@shared/ui";
import { deadlineToIso, isoToDeadline } from "../lib/labels";

export type RouteSendCardProps = {
  route: SigningRoute;
  preview: SigningRoutePreview | undefined;
  previewFailed: boolean;
  resend: boolean;
  personaLabel: (persona: string) => string;
  sending: boolean;
  error: string | null;
  /** Срок и сообщение: сохраняются вместе с остальным маршрутом (PUT). */
  onSaveTexts: (texts: {
    deadline: string | null;
    message: string | null;
  }) => void;
  onSend: (texts: {
    deadline: string | null;
    message: string | null;
    sign: { passphrase: string | null } | null;
  }) => void;
};

/** Низ экрана: срок, сообщение подписантам, что мешает, и «Отправить на подписание». */
export const RouteSendCard = ({
  route,
  preview,
  previewFailed,
  resend,
  personaLabel,
  sending,
  error,
  onSaveTexts,
  onSend,
}: RouteSendCardProps) => {
  const { t, i18n } = useTranslation("signingRouteEditor");
  const [day, setDay] = useState(isoToDeadline(route.deadline));
  const [message, setMessage] = useState(route.message ?? "");
  const [passphrase, setPassphrase] = useState("");

  const texts = () => ({
    deadline: deadlineToIso(day),
    message: message.trim() === "" ? null : message.trim(),
  });
  const dirty = () => {
    const next = texts();
    return next.deadline !== route.deadline || next.message !== route.message;
  };
  const saveIfDirty = () => {
    if (dirty()) onSaveTexts(texts());
  };

  const people = new Map(
    (preview?.participants ?? []).map((p) => [p.participant_id, p]),
  );
  const docName = (docId: string | null) => {
    const doc = route.docs.find((d) => d.doc_id === docId);
    return doc
      ? pickLocalized(doc.name, i18n.language, doc.doc_id)
      : (docId ?? "");
  };
  const slotName = (b: SigningRouteBlocker) => {
    const slot = route.docs
      .find((d) => d.doc_id === b.doc_id)
      ?.slots.find((s) => s.slot_id === b.slot_id);
    return slot
      ? pickLocalized(slot.label, i18n.language, slot.slot_id)
      : (b.slot_id ?? "");
  };
  const blockerText = (b: SigningRouteBlocker): string => {
    const who = b.participant_id ? people.get(b.participant_id) : undefined;
    switch (b.code) {
      case "not_built":
        return t("blocker.not_built", { doc: docName(b.doc_id) });
      case "doc_in_other_route":
        return t("blocker.doc_in_other_route", { doc: docName(b.doc_id) });
      case "participant_missing":
        return t("blocker.participant_missing", {
          who: who ? personaLabel(who.persona) : "",
        });
      case "slot_unassigned":
        return t("blocker.slot_unassigned", {
          slot: slotName(b),
          doc: docName(b.doc_id),
        });
      case "sender_not_ready":
        return t("blocker.sender_not_ready");
      case "no_participants":
        return t("blocker.no_participants");
      default:
        return t("blocker.unknown", { code: b.code });
    }
  };

  const key = preview?.sender_key ?? null;
  const canSign = preview?.can_send_and_sign === true && key !== null;
  const needsPass = canSign && key.protected;
  const blockers = preview?.blockers ?? [];
  const visual = preview?.visual_step;

  return (
    <div className="flex flex-col" style={{ gap: "0.75rem" }}>
      <label
        className="flex flex-col"
        style={{ gap: "0.25rem", fontSize: "0.75rem" }}
      >
        {t("send.deadline")}
        <input
          type="date"
          className="input"
          value={day}
          onChange={(e) => {
            setDay(e.target.value);
          }}
          onBlur={saveIfDirty}
          data-testid="route-deadline"
        />
      </label>
      <label
        className="flex flex-col"
        style={{ gap: "0.25rem", fontSize: "0.75rem" }}
      >
        {t("send.message")}
        <textarea
          className="textarea"
          rows={3}
          maxLength={SIGNING_TEXT_MAX}
          value={message}
          placeholder={t("send.messagePlaceholder")}
          onChange={(e) => {
            setMessage(e.target.value);
          }}
          onBlur={saveIfDirty}
          style={{
            resize: "vertical",
            minHeight: "4rem",
            padding: "0.375rem 0.5rem",
          }}
          data-testid="route-message"
        />
      </label>

      {previewFailed && <Notice tone="err" text={t("send.previewFailed")} />}
      {!preview && !previewFailed && <Spinner size="sm" />}
      {preview && (
        <>
          {visual !== undefined && (
            <span className="dim" style={{ fontSize: "0.71875rem" }}>
              {visual === 0
                ? t("send.freezeAtSend")
                : t("send.freezeAfter", { n: visual })}
            </span>
          )}
          {preview.participants
            .filter((p) => p.chooses_method)
            .map((p) => (
              <span
                key={p.participant_id}
                className="dim"
                style={{ fontSize: "0.71875rem" }}
              >
                {t("send.choosesMethod", {
                  who: p.name ?? personaLabel(p.persona),
                })}
              </span>
            ))}
          {blockers.length > 0 ? (
            <div
              className="flex flex-col"
              style={{ gap: "0.25rem" }}
              data-testid="route-blockers"
            >
              <strong style={{ fontSize: "0.75rem" }}>
                {t("send.blockers")}
              </strong>
              <ul
                style={{
                  margin: 0,
                  paddingLeft: "1.125rem",
                  fontSize: "0.71875rem",
                  color: "var(--c-warn)",
                  lineHeight: 1.6,
                }}
              >
                {blockers.map((b, i) => (
                  <li key={`${b.code}-${String(i)}`}>{blockerText(b)}</li>
                ))}
              </ul>
            </div>
          ) : (
            <span style={{ fontSize: "0.75rem", color: "var(--c-ok)" }}>
              {t("send.ready")}
            </span>
          )}
          {canSign && (
            <span className="dim" style={{ fontSize: "0.71875rem" }}>
              {t("send.signWith", { label: key.label, signer: key.signer })}
            </span>
          )}
          {needsPass && (
            <label
              className="flex flex-col"
              style={{ gap: "0.25rem", fontSize: "0.75rem" }}
            >
              {t("send.passphrase")}
              <input
                type="password"
                className="input"
                autoComplete="off"
                value={passphrase}
                onChange={(e) => {
                  setPassphrase(e.target.value);
                }}
              />
            </label>
          )}
        </>
      )}

      {error && (
        <div role="alert">
          <Notice tone="err" text={error} />
        </div>
      )}

      <div className="flex" style={{ gap: "0.5rem", flexWrap: "wrap" }}>
        {canSign && (
          <button
            type="button"
            className="btn primary"
            disabled={sending || (needsPass && passphrase === "")}
            onClick={() => {
              onSend({
                ...texts(),
                sign: { passphrase: needsPass ? passphrase : null },
              });
            }}
            data-testid="route-send-sign"
          >
            {sending && <Spinner size="sm" />}
            {t("send.sendAndSign")}
          </button>
        )}
        <button
          type="button"
          className={canSign ? "btn" : "btn primary"}
          disabled={sending || preview?.can_send !== true}
          onClick={() => {
            onSend({ ...texts(), sign: null });
          }}
          data-testid="route-send"
        >
          {sending && !canSign && <Spinner size="sm" />}
          <Send size="0.75rem" aria-hidden="true" />
          {resend ? t("send.resend") : t("send.send")}
        </button>
      </div>
    </div>
  );
};
