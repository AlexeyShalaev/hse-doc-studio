import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { AlertTriangle, KeyRound } from "lucide-react";
import {
  signatureApi,
  useAttachDetachedSignature,
  useFreezePdf,
  useSetSlotSigner,
} from "@entities/signature";
import { localeTag, toast } from "@shared/lib";
import { Modal } from "@shared/ui";
import { Spinner } from "@shared/ui/Spinner";
import {
  CadesError,
  exportCertificatePem,
  listCertificates,
  loadCadesPlugin,
  signDetached,
  type CadesCertificate,
  type CadesPlugin,
} from "../lib/cades";

export type CryptoProSignDialogProps = {
  projectId: string;
  docId: string;
  slotId: string;
  onClose: () => void;
};

type Phase =
  | { kind: "loading" }
  | { kind: "error"; code: CadesError["code"]; message: string }
  | { kind: "pick"; api: CadesPlugin; certs: CadesCertificate[] }
  | { kind: "working"; step: "plate" | "freeze" | "sign" | "attach" };

const fmt = (d: Date): string =>
  d.toLocaleDateString(localeTag(), {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });

/** Подпись УКЭП с токена через КриптоПро ЭЦП Browser plug-in, одним окном. */
export const CryptoProSignDialog = ({
  projectId,
  docId,
  slotId,
  onClose,
}: CryptoProSignDialogProps) => {
  const { t } = useTranslation("signatureStamper");
  const [phase, setPhase] = useState<Phase>({ kind: "loading" });
  const [thumb, setThumb] = useState("");
  const [attempt, setAttempt] = useState(0);
  const setSigner = useSetSlotSigner();
  const freeze = useFreezePdf();
  const attach = useAttachDetachedSignature();

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const api = await loadCadesPlugin();
        const certs = await listCertificates(api);
        if (cancelled) return;
        if (certs.length === 0) {
          setPhase({ kind: "error", code: "no-certs", message: "" });
          return;
        }
        setThumb(certs[0]?.thumbprint ?? "");
        setPhase({ kind: "pick", api, certs });
      } catch (err) {
        if (cancelled) return;
        const code = err instanceof CadesError ? err.code : "failed";
        setPhase({
          kind: "error",
          code,
          message: err instanceof Error ? err.message : String(err),
        });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  const run = async (api: CadesPlugin, certs: CadesCertificate[]) => {
    const chosen = certs.find((c) => c.thumbprint === thumb);
    if (!chosen) return;
    try {
      // 1. Плашка берёт данные подписанта из открытой части сертификата.
      setPhase({ kind: "working", step: "plate" });
      const pem = await exportCertificatePem(api, chosen.thumbprint);
      await setSigner.mutateAsync({
        projectId,
        slotId,
        file: new File([pem], "certificate.pem", {
          type: "application/x-pem-file",
        }),
      });

      // 2. Плашка попадает в PDF до подписи: фиксируем заново, если нужно.
      setPhase({ kind: "working", step: "freeze" });
      const state = await signatureApi.getState(projectId);
      const frozen = state.frozen[docId];
      if (!frozen || frozen.plate_outdated || frozen.stale) {
        await freeze.mutateAsync({ projectId, docId });
      }

      // 3. Подпись на токене (плагин сам спросит PIN).
      setPhase({ kind: "working", step: "sign" });
      const pdf = await signatureApi.downloadFrozenPdf(projectId, docId);
      const signature = await signDetached(api, chosen.thumbprint, pdf);

      // 4. Студия проверяет подпись по зафиксированному PDF.
      setPhase({ kind: "working", step: "attach" });
      const res = await attach.mutateAsync({
        projectId,
        docId,
        slotId,
        // TS 6: Uint8Array<ArrayBufferLike> — не BlobPart; копия даёт ArrayBuffer.
        file: new File([new Uint8Array(signature)], "signature.sig", {
          type: "application/octet-stream",
        }),
      });
      if (res.signature.verdict === "valid") {
        toast.success(t("detached.slot.attachedToast"));
      } else {
        toast.info(t(`detached.verdict.${res.signature.verdict}`));
      }
      onClose();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err));
      setPhase({ kind: "pick", api, certs });
    }
  };

  const working = phase.kind === "working";

  return (
    <Modal
      isOpen
      onClose={working ? () => undefined : onClose}
      width={520}
      title={t("detached.cryptopro.title")}
      footer={
        <>
          <button
            type="button"
            className="btn"
            onClick={onClose}
            disabled={working}
          >
            {t("detached.sign.cancel")}
          </button>
          {phase.kind === "error" && (
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => {
                setPhase({ kind: "loading" });
                setAttempt((n) => n + 1);
              }}
            >
              {t("detached.cryptopro.retry")}
            </button>
          )}
          {phase.kind === "pick" && (
            <button
              type="button"
              className="btn btn-primary"
              disabled={!thumb}
              onClick={() => {
                void run(phase.api, phase.certs);
              }}
            >
              <KeyRound size={12} />
              {t("detached.cryptopro.sign")}
            </button>
          )}
        </>
      }
    >
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {phase.kind === "loading" && (
          <div className="flex items-center gap-2" style={{ fontSize: 12 }}>
            <Spinner size="sm" />
            {t("detached.cryptopro.loading")}
          </div>
        )}

        {phase.kind === "error" && (
          <div
            className="flex items-start gap-2"
            style={{ fontSize: 12, lineHeight: 1.55, color: "var(--fg-1)" }}
          >
            <AlertTriangle
              size={14}
              style={{ color: "var(--c-warn)", flexShrink: 0, marginTop: 2 }}
            />
            <div>
              <div style={{ fontWeight: 500 }}>
                {t(`detached.cryptopro.error.${phase.code}.title`)}
              </div>
              <div>{t(`detached.cryptopro.error.${phase.code}.hint`)}</div>
              {phase.code === "failed" && phase.message && (
                <div className="mono dim" style={{ fontSize: 10.5 }}>
                  {phase.message}
                </div>
              )}
            </div>
          </div>
        )}

        {phase.kind === "pick" && (
          <>
            <div style={{ fontSize: 12, color: "var(--fg-2)" }}>
              {t("detached.cryptopro.pick")}
            </div>
            {phase.certs.map((c) => (
              <label
                key={c.thumbprint}
                style={{
                  display: "flex",
                  gap: 8,
                  alignItems: "flex-start",
                  padding: "8px 10px",
                  borderRadius: 6,
                  cursor: "pointer",
                  border: `1px solid ${
                    thumb === c.thumbprint ? "var(--accent)" : "var(--border)"
                  }`,
                  background: "var(--bg-1)",
                }}
              >
                <input
                  type="radio"
                  name="cades-cert"
                  checked={thumb === c.thumbprint}
                  onChange={() => {
                    setThumb(c.thumbprint);
                  }}
                />
                <span style={{ fontSize: 12, lineHeight: 1.45 }}>
                  <strong>{c.subject}</strong>
                  <br />
                  <span className="dim">
                    {c.issuer} · {fmt(c.validFrom)} - {fmt(c.validTo)}
                  </span>
                </span>
              </label>
            ))}
            <div
              style={{ fontSize: 11, color: "var(--fg-3)", lineHeight: 1.5 }}
            >
              {t("detached.cryptopro.note")}
            </div>
          </>
        )}

        {phase.kind === "working" && (
          <div className="flex items-center gap-2" style={{ fontSize: 12 }}>
            <Spinner size="sm" />
            {t(`detached.cryptopro.step.${phase.step}`)}
          </div>
        )}
      </div>
    </Modal>
  );
};
