import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { AlertTriangle, Check, Clock, X } from "lucide-react";
import { isAxiosError } from "axios";
import {
  usePreviewSignSubmission,
  useSignSubmission,
} from "@entities/signature";
import { useSigningIdentities } from "@entities/signing-identity";
import { RouteWaitNote } from "@features/signing-route-progress";
import { pickLocalized } from "@shared/lib";
import { Modal } from "@shared/ui";
import { Spinner } from "@shared/ui/Spinner";

export type SignSubmissionDialogProps = {
  projectId: string;
  profileId: string;
  author: string | null;
  lang: string;
  docName: (docId: string) => string;
  onClose: () => void;
};

const errorText = (error: unknown): string => {
  if (isAxiosError<{ detail?: unknown }>(error)) {
    const detail = error.response?.data.detail;
    if (typeof detail === "string") return detail;
    if (detail != null && typeof detail === "object" && "message" in detail) {
      return String(detail.message);
    }
  }
  return error instanceof Error ? error.message : String(error);
};

/**
 * «Подписать комплект»: одно окно на все документы точки сдачи. Сначала
 * предпросмотр — что будет зафиксировано, чьи подписи это сбросит, какие свои
 * слоты и каким ключом подпишутся. Подпись отправляет отпечатки документов из
 * предпросмотра: если между ними документ пересобрали, сервер откажет, и
 * человек посмотрит заново (подпись относится к версии, которую он видел).
 */
export const SignSubmissionDialog = ({
  projectId,
  profileId,
  author,
  lang,
  docName,
  onClose,
}: SignSubmissionDialogProps) => {
  const { t } = useTranslation("signatureStamper");
  const { data: identities } = useSigningIdentities();
  const preview = usePreviewSignSubmission();
  const sign = useSignSubmission();
  const [identityId, setIdentityId] = useState<string | null>(null);
  const [passphrase, setPassphrase] = useState("");
  const [confirmReset, setConfirmReset] = useState(false);

  const { mutate: runPreview } = preview;
  useEffect(() => {
    runPreview({
      projectId,
      body: { profile_id: profileId, author, identity_id: identityId },
    });
  }, [runPreview, projectId, profileId, author, identityId]);

  const data = preview.data;
  const resets = (data?.docs ?? []).flatMap((doc) =>
    doc.needs_freeze ? doc.resets : [],
  );
  const result = sign.data;
  // Документы, которые держит идущий маршрут и которые сейчас не подписать: почему и когда,
  // объясняет пояснение маршрута, одно на маршрут.
  const isHeld = (doc: { route_id: string | null; blocker: string }) =>
    doc.route_id != null && doc.blocker !== "";
  const heldRoutes = [
    ...new Set(
      (data?.docs ?? []).flatMap((doc) =>
        isHeld(doc) && doc.route_id != null ? [doc.route_id] : [],
      ),
    ),
  ];
  const canSign =
    data != null &&
    data.to_sign + data.docs.filter((d) => d.needs_freeze).length > 0 &&
    (resets.length === 0 || confirmReset) &&
    (!data.needs_passphrase || passphrase !== "") &&
    !sign.isPending &&
    result == null;

  const submit = () => {
    if (data == null) return;
    sign.mutate({
      projectId,
      body: {
        profile_id: profileId,
        author,
        identity_id: identityId ?? data.key?.id ?? null,
        passphrase,
        confirm_reset: confirmReset,
        expected: Object.fromEntries(data.docs.map((d) => [d.doc_id, d.token])),
      },
    });
  };

  return (
    <Modal
      isOpen
      onClose={sign.isPending ? () => undefined : onClose}
      width={600}
      title={t("signSubmission.title")}
      description={t("signSubmission.description")}
      footer={
        <>
          <button
            type="button"
            className="btn"
            onClick={onClose}
            disabled={sign.isPending}
          >
            {result ? t("signSubmission.close") : t("signSubmission.cancel")}
          </button>
          {result == null && (
            <button
              type="button"
              className="btn primary"
              onClick={submit}
              disabled={!canSign}
            >
              {sign.isPending && <Spinner size="sm" />}
              {t("signSubmission.sign")}
            </button>
          )}
        </>
      }
    >
      {preview.isPending && <Spinner />}
      {preview.isError && (
        <p className="dim" style={{ color: "var(--c-err)" }}>
          {errorText(preview.error)}
        </p>
      )}
      {data != null && result == null && (
        <div className="flex flex-col" style={{ gap: "0.75rem" }}>
          <label className="flex flex-col" style={{ gap: "0.25rem" }}>
            <span style={{ fontSize: "0.75rem" }}>
              {t("signSubmission.key")}
            </span>
            <select
              className="input"
              value={identityId ?? data.key?.id ?? ""}
              onChange={(event) => {
                setIdentityId(
                  event.target.value === "" ? null : event.target.value,
                );
              }}
            >
              {data.key == null && (
                <option value="">{t("signSubmission.noKey")}</option>
              )}
              {(identities ?? []).map((identity) => (
                <option key={identity.id} value={identity.id}>
                  {identity.label}
                </option>
              ))}
            </select>
          </label>
          {data.needs_passphrase && (
            <label className="flex flex-col" style={{ gap: "0.25rem" }}>
              <span style={{ fontSize: "0.75rem" }}>
                {t("signSubmission.passphrase")}
              </span>
              <input
                className="input"
                type="password"
                autoComplete="off"
                value={passphrase}
                onChange={(event) => {
                  setPassphrase(event.target.value);
                }}
              />
            </label>
          )}

          {data.docs.length === 0 && (
            <p className="dim">{t("signSubmission.nothing")}</p>
          )}
          {data.docs.map((doc) => (
            <div
              key={doc.doc_id}
              className="flex flex-col"
              style={{ gap: "0.25rem" }}
            >
              <strong style={{ fontSize: "0.8125rem" }}>
                {docName(doc.doc_id)}
              </strong>
              {doc.needs_freeze && (
                <span className="dim" style={{ fontSize: "0.71875rem" }}>
                  {t("signSubmission.willFreeze")}
                </span>
              )}
              {/* Документ на подписании по маршруту: комплект его не трогает, почему и когда, сказано ниже. */}
              {doc.blocker !== "" && (
                <span
                  className={isHeld(doc) ? "dim" : undefined}
                  style={{
                    fontSize: "0.71875rem",
                    color: isHeld(doc) ? undefined : "var(--c-err)",
                  }}
                  data-testid={
                    isHeld(doc)
                      ? `sign-submission-route-${doc.doc_id}`
                      : undefined
                  }
                >
                  {doc.blocker}
                </span>
              )}
              {doc.slots.map((slot) => (
                <span
                  key={slot.slot_id}
                  className="flex items-center"
                  style={{ gap: "0.375rem", fontSize: "0.75rem" }}
                >
                  {slot.blocker === "" ? (
                    <Check size="0.75rem" style={{ color: "var(--c-ok)" }} />
                  ) : isHeld(doc) ? (
                    <Clock size="0.75rem" style={{ color: "var(--fg-3)" }} />
                  ) : (
                    <AlertTriangle
                      size="0.75rem"
                      style={{ color: "var(--c-warn)" }}
                    />
                  )}
                  {pickLocalized(slot.label, lang, slot.slot_id)}
                  <span className="chip subtle">
                    {t(`signSubmission.method.${slot.method}`)}
                  </span>
                  <span className="dim">
                    {isHeld(doc) && slot.blocker !== ""
                      ? t("signingProgress:wait.heldSlot")
                      : slot.blocker !== ""
                        ? slot.blocker
                        : t(`signSubmission.action.${slot.action}`)}
                  </span>
                </span>
              ))}
            </div>
          ))}

          {heldRoutes.map((routeId) => (
            <RouteWaitNote
              key={routeId}
              projectId={projectId}
              routeId={routeId}
            />
          ))}

          {resets.length > 0 && (
            <label
              className="flex items-start"
              style={{
                gap: "0.5rem",
                fontSize: "0.75rem",
                color: "var(--c-warn)",
              }}
            >
              <input
                type="checkbox"
                checked={confirmReset}
                onChange={(event) => {
                  setConfirmReset(event.target.checked);
                }}
              />
              <span>
                {t("signSubmission.confirmReset", {
                  names: resets
                    .map(
                      (r) =>
                        r.signer || pickLocalized(r.label, lang, r.slot_id),
                    )
                    .join(", "),
                })}
              </span>
            </label>
          )}
          {sign.isError && (
            <p style={{ color: "var(--c-err)", fontSize: "0.75rem" }}>
              {errorText(sign.error)}
            </p>
          )}
        </div>
      )}
      {result != null && (
        <div className="flex flex-col" style={{ gap: "0.375rem" }}>
          <strong style={{ fontSize: "0.8125rem" }}>
            {t("signSubmission.done", {
              signed: result.plan.signed,
              total: result.plan.total,
            })}
          </strong>
          {result.results.map((r) => (
            <span
              key={`${r.doc_id}/${r.slot_id}`}
              className="flex items-center"
              style={{ gap: "0.375rem", fontSize: "0.75rem" }}
            >
              {r.ok ? (
                <Check size="0.75rem" style={{ color: "var(--c-ok)" }} />
              ) : (
                <X size="0.75rem" style={{ color: "var(--c-err)" }} />
              )}
              {docName(r.doc_id)} · {r.slot_id}
              {r.message !== "" && <span className="dim">{r.message}</span>}
            </span>
          ))}
        </div>
      )}
    </Modal>
  );
};
