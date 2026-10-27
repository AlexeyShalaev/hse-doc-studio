import { useState } from "react";
import { ShieldAlert, ShieldQuestion } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useUpdateHostSettings } from "@entities/git-remote";
import { describeGitError, type GitTlsCertificate } from "@entities/git-sync";
import { Modal } from "@shared/ui/Modal";
import { Notice } from "@shared/ui/ConflictKit";
import { CopyField } from "@shared/ui/CopyField";
import { Spinner } from "@shared/ui/Spinner";
import { formatDate } from "../lib/formatDate";
import { pemProblem } from "../lib/pem";
import { CaCertificateInput } from "./CaCertificateInput";
import { ConfirmCheck } from "./ConfirmCheck";

export type TlsTrustMode = "untrusted" | "pin_mismatch";
type Choice = "ca" | "pin";

export type TlsTrustDialogProps = {
  isOpen: boolean;
  mode: TlsTrustMode;
  host: string;
  port: number | null;
  /** Сертификат, который сервер предъявил сейчас. */
  certificate: GitTlsCertificate | null;
  /** Только pin_mismatch: отпечаток, закреплённый раньше. */
  expected?: string | null;
  /** Только pin_mismatch: отпечаток, который сервер предъявил сейчас. */
  actual?: string | null;
  onTrusted: () => void;
  onClose: () => void;
};

const CertificateFacts = ({ cert }: { cert: GitTlsCertificate }) => {
  const { t } = useTranslation("gitAccess");
  const rows: [string, string][] = [
    [t("tls.facts.subject"), cert.subject],
    [t("tls.facts.issuer"), cert.issuer],
    [
      t("tls.facts.valid"),
      t("tls.facts.validRange", {
        from: formatDate(cert.not_before),
        to: formatDate(cert.not_after),
      }),
    ],
  ];
  return (
    <dl
      data-testid="tls-certificate"
      style={{
        margin: 0,
        display: "grid",
        gridTemplateColumns: "max-content 1fr",
        columnGap: 14,
        rowGap: 4,
        fontSize: 12,
      }}
    >
      {rows.map(([label, value]) => (
        <div key={label} style={{ display: "contents" }}>
          <dt className="dim">{label}</dt>
          <dd
            className="mono"
            style={{ margin: 0, minWidth: 0, wordBreak: "break-all" }}
          >
            {value}
          </dd>
        </div>
      ))}
      {cert.self_signed && (
        <div style={{ display: "contents" }}>
          <dt className="dim">{t("tls.facts.kind")}</dt>
          <dd style={{ margin: 0 }}>
            <span className="chip subtle">{t("tls.facts.selfSigned")}</span>
          </dd>
        </div>
      )}
    </dl>
  );
};

// Сертификат внутреннего сервера не от известного центра. Проверку не
// отключаем: человек либо добавляет сертификат центра выдачи (CA) для этого
// сервера, либо закрепляет отпечаток сертификата, как ключ сервера в ssh.
export const TlsTrustDialog = ({
  isOpen,
  mode,
  host,
  port,
  certificate,
  expected = null,
  actual = null,
  onTrusted,
  onClose,
}: TlsTrustDialogProps) => {
  const { t } = useTranslation("gitAccess");
  const save = useUpdateHostSettings();
  const mismatch = mode === "pin_mismatch";
  const defaultChoice: Choice =
    mismatch || certificate?.self_signed ? "pin" : "ca";
  const [picked, setPicked] = useState<Choice | null>(null);
  const choice = picked ?? defaultChoice;
  const [pem, setPem] = useState("");
  const [checked, setChecked] = useState(false);
  const [typedHost, setTypedHost] = useState("");
  const [error, setError] = useState<string | null>(null);

  const reset = (): void => {
    setPicked(null);
    setPem("");
    setChecked(false);
    setTypedHost("");
    setError(null);
  };

  // Окно остаётся смонтированным, пока родитель его закрывает: состояние
  // сбрасываем в момент закрытия, а не при следующем показе.
  const [wasOpen, setWasOpen] = useState(isOpen);
  if (wasOpen !== isOpen) {
    setWasOpen(isOpen);
    if (!isOpen) reset();
  }
  const close = (): void => {
    if (save.isPending) return;
    reset();
    onClose();
  };

  const problem = pemProblem(pem);
  const canAddCa = problem === null;
  // Что закрепить: отпечаток сертификата или, при смене, тот, что сервер прислал сейчас.
  const newFingerprint = certificate?.fingerprint_sha256 ?? actual;
  const canPin =
    newFingerprint !== null &&
    checked &&
    (!mismatch || typedHost.trim().toLowerCase() === host.toLowerCase());

  const submit = async (): Promise<void> => {
    setError(null);
    try {
      await save.mutateAsync(
        choice === "ca"
          ? {
              host,
              port,
              ca_pem: pem.trim(),
              // Доверие центру выдачи заменяет старое закрепление.
              ...(mismatch ? { pinned_fingerprint: null } : {}),
            }
          : { host, port, pinned_fingerprint: newFingerprint },
      );
      reset();
      onTrusted();
    } catch (caught) {
      setError(describeGitError(caught, t("tls.failed")));
    }
  };

  const Icon = mismatch ? ShieldAlert : ShieldQuestion;
  const hostLabel = port ? `${host}:${String(port)}` : host;

  return (
    <Modal
      isOpen={isOpen}
      onClose={close}
      width={620}
      title={
        <span className="flex items-center" style={{ gap: 8 }}>
          <Icon
            size={17}
            aria-hidden="true"
            style={{ color: mismatch ? "var(--c-err)" : "var(--c-warn)" }}
          />
          {mismatch
            ? t("tls.mismatchTitle", { host: hostLabel })
            : t("tls.untrustedTitle", { host: hostLabel })}
        </span>
      }
      description={mismatch ? t("tls.mismatchText") : t("tls.untrustedText")}
      footer={
        <>
          <button
            type="button"
            className="btn"
            autoFocus
            onClick={close}
            disabled={save.isPending}
          >
            {t("tls.cancel")}
          </button>
          <button
            type="button"
            className={
              mismatch && choice === "pin" ? "btn danger" : "btn primary"
            }
            disabled={save.isPending || (choice === "ca" ? !canAddCa : !canPin)}
            data-testid="tls-submit"
            onClick={() => {
              void submit();
            }}
          >
            {save.isPending && <Spinner size="sm" />}
            {choice === "ca"
              ? t("tls.ca.submit")
              : mismatch
                ? t("tls.pin.replace")
                : t("tls.pin.submit")}
          </button>
        </>
      }
    >
      <div
        className="flex flex-col"
        style={{ gap: 12 }}
        data-testid={`tls-dialog-${mode}`}
      >
        {mismatch && (
          <Notice tone="err" role="alert" text={t("tls.mismatchWarning")} />
        )}

        <div
          className="seg"
          role="group"
          aria-label={t("tls.choice.label")}
          style={{ alignSelf: "flex-start", flexWrap: "wrap" }}
        >
          {(["ca", "pin"] as const).map((value) => (
            <button
              key={value}
              type="button"
              aria-pressed={choice === value}
              className={choice === value ? "active" : undefined}
              onClick={() => {
                setPicked(value);
                setError(null);
              }}
            >
              {t(`tls.choice.${value}`)}
            </button>
          ))}
        </div>

        {choice === "ca" ? (
          <div
            className="flex flex-col"
            style={{ gap: 10 }}
            data-testid="tls-ca"
          >
            <p style={{ margin: 0, fontSize: 12.5, lineHeight: 1.5 }}>
              {t("tls.ca.text")}
            </p>
            <CaCertificateInput
              value={pem}
              onChange={setPem}
              onReadError={() => {
                setError(t("tls.ca.readFailed"));
              }}
              idPrefix="tls-ca"
            />
            <p className="dim" style={{ margin: 0, fontSize: 11.5 }}>
              {t("tls.ca.stored", { host: hostLabel })}
              {mismatch ? ` ${t("tls.ca.replacesPin")}` : ""}
            </p>
          </div>
        ) : (
          <div
            className="flex flex-col"
            style={{ gap: 10 }}
            data-testid="tls-pin"
          >
            {newFingerprint !== null ? (
              <>
                <p style={{ margin: 0, fontSize: 12.5, lineHeight: 1.5 }}>
                  {t("tls.pin.text")}
                </p>
                {certificate && <CertificateFacts cert={certificate} />}
                {mismatch && expected ? (
                  <div
                    className="flex flex-col"
                    style={{ gap: 8 }}
                    data-testid="tls-compare"
                  >
                    <div>
                      <div
                        className="dim"
                        style={{ fontSize: 11.5, marginBottom: 4 }}
                      >
                        {t("tls.pin.expected")}
                      </div>
                      <CopyField
                        value={expected}
                        label={t("tls.pin.expected")}
                      />
                    </div>
                    <div>
                      <div
                        style={{
                          fontSize: 11.5,
                          marginBottom: 4,
                          color: "var(--c-err)",
                        }}
                      >
                        {t("tls.pin.actual")}
                      </div>
                      <CopyField
                        value={newFingerprint}
                        label={t("tls.pin.actual")}
                      />
                    </div>
                  </div>
                ) : (
                  <div>
                    <div
                      className="dim"
                      style={{ fontSize: 11.5, marginBottom: 4 }}
                    >
                      {t("tls.pin.fingerprint")}
                    </div>
                    <CopyField
                      value={newFingerprint}
                      label={t("tls.pin.fingerprint")}
                    />
                  </div>
                )}
                <ConfirmCheck
                  checked={checked}
                  onChange={setChecked}
                  testId="tls-pin-confirm"
                >
                  {t("tls.pin.confirm")}
                </ConfirmCheck>
                {mismatch && (
                  <div className="field">
                    <label htmlFor="tls-confirm-host">
                      {t("tls.pin.typeHost", { host })}
                    </label>
                    <input
                      id="tls-confirm-host"
                      type="text"
                      className="input mono"
                      value={typedHost}
                      autoComplete="off"
                      spellCheck={false}
                      placeholder={host}
                      onChange={(event) => {
                        setTypedHost(event.target.value);
                      }}
                    />
                  </div>
                )}
              </>
            ) : (
              <Notice
                tone="warn"
                role="status"
                text={t("tls.pin.noCertificate")}
              />
            )}
          </div>
        )}

        <p className="dim" style={{ margin: 0, fontSize: 11.5 }}>
          {t("tls.noDisable")}
        </p>
        {error && <Notice tone="err" role="alert" text={error} />}
      </div>
    </Modal>
  );
};
