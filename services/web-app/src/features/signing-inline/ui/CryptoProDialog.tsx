import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { AlertTriangle } from "lucide-react";
import {
  CadesError,
  listCertificates,
  loadCadesPlugin,
  type CadesCertificate,
  type CadesPlugin,
} from "@features/signature-stamper";
import { localeTag } from "@shared/lib";
import { Button, Modal, Spinner } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";

export type CryptoProDialogProps = {
  /** Что сделать с выбранным сертификатом: данные для плашки или подпись итогового PDF. */
  purpose: "plate" | "sign";
  busy: boolean;
  /** Подпись главной кнопки для `sign`. */
  submitLabel: string;
  /** Текст отказа прошлой попытки. */
  error: string | null;
  onClose: () => void;
  onPick: (api: CadesPlugin, thumbprint: string) => void;
};

type Phase =
  | { kind: "loading" }
  | { kind: "error"; code: CadesError["code"]; message: string }
  | { kind: "pick"; api: CadesPlugin; certs: CadesCertificate[] };

const day = (date: Date): string =>
  date.toLocaleDateString(localeTag(), {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });

/**
 * Сертификат из КриптоПро ЭЦП Browser plug-in. Закрытый ключ остаётся на токене: плагин
 * подписывает итоговый PDF в браузере, на сервер уходит готовая подпись (раздел 6.10).
 */
export const CryptoProDialog = ({
  purpose,
  busy,
  submitLabel,
  error,
  onClose,
  onPick,
}: CryptoProDialogProps) => {
  const { t } = useTranslation("signing");
  const [phase, setPhase] = useState<Phase>({ kind: "loading" });
  const [thumbprint, setThumbprint] = useState("");
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    // Объект, а не переменная: окно могли закрыть, пока плагин отвечал.
    const live = { current: true };
    void (async () => {
      try {
        const api = await loadCadesPlugin();
        const certs = await listCertificates(api);
        if (!live.current) return;
        if (certs.length === 0) {
          setPhase({ kind: "error", code: "no-certs", message: "" });
          return;
        }
        setThumbprint(certs[0]?.thumbprint ?? "");
        setPhase({ kind: "pick", api, certs });
      } catch (err) {
        if (!live.current) return;
        setPhase({
          kind: "error",
          code: err instanceof CadesError ? err.code : "failed",
          message: err instanceof Error ? err.message : String(err),
        });
      }
    })();
    return () => {
      live.current = false;
    };
  }, [attempt]);

  return (
    <Modal
      isOpen
      onClose={busy ? () => undefined : onClose}
      width={520}
      title={t("cryptopro.title")}
      footer={
        <>
          <Button
            type="button"
            variant="secondary"
            disabled={busy}
            onClick={onClose}
          >
            {t("cryptopro.cancel")}
          </Button>
          {phase.kind === "error" && (
            <Button
              type="button"
              onClick={() => {
                setPhase({ kind: "loading" });
                setAttempt((n) => n + 1);
              }}
              data-testid="signing-cryptopro-retry"
            >
              {t("cryptopro.retry")}
            </Button>
          )}
          {phase.kind === "pick" && (
            <Button
              type="button"
              disabled={busy || thumbprint === ""}
              onClick={() => {
                onPick(phase.api, thumbprint);
              }}
              data-testid="signing-cryptopro-submit"
            >
              {busy
                ? t("actions.working")
                : purpose === "plate"
                  ? t("cryptopro.usePlate")
                  : submitLabel}
            </Button>
          )}
        </>
      }
    >
      <div
        className="flex flex-col"
        style={{ gap: "0.625rem", fontSize: "0.78125rem", lineHeight: 1.5 }}
        data-testid="signing-cryptopro"
        data-phase={phase.kind}
      >
        {phase.kind === "loading" && (
          <div className="flex items-center" style={{ gap: "0.5rem" }}>
            <Spinner size="sm" />
            {t("cryptopro.loading")}
          </div>
        )}
        {phase.kind === "error" && (
          <div className="flex items-start" style={{ gap: "0.5rem" }}>
            <AlertTriangle
              size="0.875rem"
              aria-hidden
              style={{
                color: "var(--c-warn)",
                flexShrink: 0,
                marginTop: "0.1875rem",
              }}
            />
            <div>
              <strong>
                {t(
                  `signatureStamper:detached.cryptopro.error.${phase.code}.title`,
                )}
              </strong>
              <div>
                {t(
                  `signatureStamper:detached.cryptopro.error.${phase.code}.hint`,
                )}
              </div>
              {phase.code === "failed" && phase.message && (
                <div className="mono dim">{phase.message}</div>
              )}
            </div>
          </div>
        )}
        {phase.kind === "pick" && (
          <>
            <div style={{ color: "var(--fg-2)" }}>{t("cryptopro.pick")}</div>
            {phase.certs.map((cert) => (
              <label
                key={cert.thumbprint}
                className="sgi-way"
                data-active={thumbprint === cert.thumbprint}
              >
                <input
                  type="radio"
                  name="signing-cades-cert"
                  checked={thumbprint === cert.thumbprint}
                  disabled={busy}
                  onChange={() => {
                    setThumbprint(cert.thumbprint);
                  }}
                />
                <span>
                  <strong>{cert.subject}</strong>
                  <small>
                    {cert.issuer} · {day(cert.validFrom)} - {day(cert.validTo)}
                  </small>
                </span>
              </label>
            ))}
            {busy && purpose === "sign" && (
              <div className="flex items-center" style={{ gap: "0.5rem" }}>
                <Spinner size="sm" />
                {t("cryptopro.signing")}
              </div>
            )}
          </>
        )}
        {error && (
          <div data-testid="signing-cryptopro-error">
            <Notice tone="err" role="alert" text={error} />
          </div>
        )}
      </div>
    </Modal>
  );
};
