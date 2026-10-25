import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  AlertTriangle,
  CheckCircle2,
  Copy,
  Download,
  FileKey,
  FileUp,
  HelpCircle,
  KeyRound,
  Link2,
  Lock,
  PackageCheck,
  PenLine,
  RefreshCw,
  ShieldCheck,
  Trash2,
  XCircle,
} from "lucide-react";
import {
  signatureDownloadUrls,
  useAttachDetachedSignature,
  useClearSlotSigner,
  useCompleteChain,
  useDeleteDetachedSignature,
  useFreezePdf,
  useRecheckDetachedSignature,
  useSetSignerLevel,
  useSetSlotSigner,
  useSignDetachedInStudio,
  useTrustRoot,
  useUnfreezePdf,
} from "@entities/signature";
import {
  useGenerateOpenPgpKey,
  useSigningIdentities,
  type SigningIdentity,
} from "@entities/signing-identity";
import type {
  DetachedSignatureResponse,
  DetachedVerdict,
  FrozenPdfResponse,
  SignerInfoResponse,
} from "@shared/api/types";
import { localeTag, toast } from "@shared/lib";
import { Modal } from "@shared/ui";
import { Spinner } from "@shared/ui/Spinner";
import { CryptoProSignDialog } from "./CryptoProSignDialog";

const downloadUrl = (url: string) => {
  window.location.assign(url);
};

// PDF заявки весит десятки КБ, а formatBytes из shared считает в ГБ/МБ (для
// образов Docker), поэтому здесь свой формат.
const formatSize = (bytes: number): string =>
  bytes < 1024 * 1024
    ? `${Math.max(1, Math.round(bytes / 1024))} KB`
    : `${(bytes / 1024 / 1024).toFixed(1)} MB`;

const formatDateTime = (iso: string): string =>
  new Date(iso).toLocaleString(localeTag(), {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });

const formatDate = (iso: string): string =>
  new Date(iso).toLocaleDateString(localeTag(), {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });

// «1.2.643.7.1.1.2.2» → понятное имя; незнакомое показываем как есть.
const OID_NAMES: Record<string, string> = {
  "1.2.643.7.1.1.2.2": "Стрибог-256",
  "1.2.643.7.1.1.2.3": "Стрибог-512",
  "1.2.643.7.1.1.3.2": "ГОСТ Р 34.10-2012 (256)",
  "1.2.643.7.1.1.3.3": "ГОСТ Р 34.10-2012 (512)",
};
const prettyAlgorithm = (raw: string): string =>
  raw
    .split(" / ")
    .map((part) => OID_NAMES[part] ?? part)
    .join(" / ");

// ── Freeze card ───────────────────────────────────────────────────────────────

export type FreezeCardProps = {
  projectId: string;
  docId: string;
  frozen: FrozenPdfResponse | undefined;
  signatureCount: number;
  pdfAvailable: boolean;
};

export const FreezeCard = ({
  projectId,
  docId,
  frozen,
  signatureCount,
  pdfAvailable,
}: FreezeCardProps) => {
  const { t } = useTranslation("signatureStamper");
  const freeze = useFreezePdf();
  const unfreeze = useUnfreezePdf();

  const doFreeze = () => {
    freeze.mutate(
      { projectId, docId },
      {
        onSuccess: (res) => {
          toast.success(t("detached.freeze.frozenToast"));
          if (res.dropped_slots.length > 0) {
            toast.info(
              t("detached.freeze.droppedToast", {
                count: res.dropped_slots.length,
              }),
            );
          }
        },
        onError: (err) => toast.error(err.message),
      },
    );
  };

  const handleFreeze = () => {
    if (frozen && signatureCount > 0) {
      if (!window.confirm(t("detached.freeze.refreezeConfirm"))) return;
    }
    doFreeze();
  };

  const handleUnfreeze = () => {
    if (!window.confirm(t("detached.freeze.unfreezeConfirm"))) return;
    unfreeze.mutate(
      { projectId, docId },
      { onError: (err) => toast.error(err.message) },
    );
  };

  const copySha = () => {
    if (!frozen) return;
    void navigator.clipboard.writeText(frozen.sha256).then(() => {
      toast.success(t("detached.freeze.copied"));
    });
  };

  const busy = freeze.isPending || unfreeze.isPending;

  return (
    <div
      style={{
        padding: "12px 14px",
        borderBottom: "1px solid var(--border)",
        display: "flex",
        flexDirection: "column",
        gap: 8,
      }}
    >
      <div className="flex items-center gap-2">
        <Lock size={13} style={{ color: "var(--fg-2)" }} />
        <strong style={{ fontSize: 12.5 }}>{t("detached.freeze.title")}</strong>
      </div>

      {!frozen && (
        <>
          <div style={{ fontSize: 11, color: "var(--fg-2)", lineHeight: 1.5 }}>
            {t("detached.freeze.intro")}
          </div>
          <div>
            <button
              type="button"
              className="btn xs"
              disabled={busy || !pdfAvailable}
              onClick={handleFreeze}
              title={pdfAvailable ? undefined : t("detached.freeze.needBuild")}
            >
              {freeze.isPending ? <Spinner size="sm" /> : <Lock size={10} />}
              {t("detached.freeze.freeze")}
            </button>
          </div>
        </>
      )}

      {frozen && (
        <>
          {!frozen.stale && frozen.plate_outdated && (
            <div
              className="flex items-start gap-2"
              style={{
                padding: "8px 10px",
                borderRadius: 6,
                background: "var(--c-warn-soft)",
                color: "var(--c-warn)",
                fontSize: 11,
                lineHeight: 1.45,
              }}
            >
              <AlertTriangle
                size={13}
                style={{ flexShrink: 0, marginTop: 1 }}
              />
              <span>{t("detached.freeze.plateOutdated")}</span>
            </div>
          )}
          {frozen.stale && (
            <div
              className="flex items-start gap-2"
              style={{
                padding: "8px 10px",
                borderRadius: 6,
                background: "var(--c-warn-soft)",
                color: "var(--c-warn)",
                fontSize: 11,
                lineHeight: 1.45,
              }}
            >
              <AlertTriangle
                size={13}
                style={{ flexShrink: 0, marginTop: 1 }}
              />
              <span>{t("detached.freeze.stale")}</span>
            </div>
          )}
          <div style={{ fontSize: 10.5, color: "var(--fg-2)" }}>
            {t("detached.freeze.frozenAt", {
              date: formatDateTime(frozen.frozen_at),
              size: formatSize(frozen.size),
            })}
          </div>
          <button
            type="button"
            className="mono flex items-center"
            onClick={copySha}
            title={t("detached.freeze.copy")}
            style={{
              gap: 6,
              fontSize: 10,
              padding: "4px 6px",
              borderRadius: 4,
              border: "1px solid var(--border)",
              background: "var(--bg-2)",
              color: "var(--fg-1)",
              cursor: "pointer",
              textAlign: "left",
              wordBreak: "break-all",
            }}
          >
            <span style={{ flex: 1 }}>
              {t("detached.freeze.sha256")}: {frozen.sha256}
            </span>
            <Copy size={10} style={{ flexShrink: 0 }} />
          </button>
          <div
            className="flex items-center"
            style={{ gap: 6, flexWrap: "wrap" }}
          >
            <button
              type="button"
              className="btn xs"
              disabled={busy || !pdfAvailable}
              onClick={handleFreeze}
            >
              {freeze.isPending ? (
                <Spinner size="sm" />
              ) : (
                <RefreshCw size={10} />
              )}
              {t("detached.freeze.refreeze")}
            </button>
            <button
              type="button"
              className="btn xs"
              onClick={() => {
                downloadUrl(signatureDownloadUrls.frozenPdf(projectId, docId));
              }}
            >
              <Download size={10} />
              {t("detached.freeze.downloadPdf")}
            </button>
            <button
              type="button"
              className="btn xs"
              title={t("detached.freeze.requestZipTitle")}
              onClick={() => {
                downloadUrl(
                  signatureDownloadUrls.signingPackage(
                    projectId,
                    docId,
                    "request",
                  ),
                );
              }}
            >
              <PackageCheck size={10} />
              {t("detached.freeze.requestZip")}
            </button>
            {signatureCount > 0 && !frozen.stale && (
              <button
                type="button"
                className="btn xs"
                onClick={() => {
                  downloadUrl(
                    signatureDownloadUrls.signingPackage(
                      projectId,
                      docId,
                      "signed",
                    ),
                  );
                }}
              >
                <PackageCheck size={10} />
                {t("detached.freeze.signedZip")}
              </button>
            )}
            <button
              type="button"
              className="btn xs ghost"
              disabled={busy}
              style={{ color: "var(--c-err)" }}
              onClick={handleUnfreeze}
            >
              <Trash2 size={10} />
              {t("detached.freeze.unfreeze")}
            </button>
          </div>
        </>
      )}
    </div>
  );
};

// ── Verdict badge ─────────────────────────────────────────────────────────────

type BadgeKind = "ok" | "err" | "warn" | "dim";

const VERDICT_STYLE: Record<BadgeKind, { color: string; background: string }> =
  {
    ok: { color: "var(--c-ok)", background: "var(--c-ok-soft)" },
    err: { color: "var(--c-err)", background: "var(--c-err-soft)" },
    warn: { color: "var(--c-warn)", background: "var(--c-warn-soft)" },
    dim: { color: "var(--fg-2)", background: "var(--bg-2)" },
  };

const VerdictBadge = ({
  verdict,
  current,
  stale,
}: {
  verdict: DetachedVerdict;
  current: boolean;
  stale: boolean;
}) => {
  const { t } = useTranslation("signatureStamper");
  let kind: BadgeKind;
  let text: string;
  let icon: React.ReactNode;
  if (stale) {
    kind = "err";
    text = t("detached.verdict.stale");
    icon = <XCircle size={11} />;
  } else if (!current) {
    kind = "err";
    text = t("detached.verdict.outdated");
    icon = <XCircle size={11} />;
  } else if (verdict === "valid") {
    kind = "ok";
    text = t("detached.verdict.valid");
    icon = <CheckCircle2 size={11} />;
  } else if (verdict === "invalid") {
    kind = "err";
    text = t("detached.verdict.invalid");
    icon = <XCircle size={11} />;
  } else if (verdict === "unknown_key") {
    kind = "warn";
    text = t("detached.verdict.unknown_key");
    icon = <HelpCircle size={11} />;
  } else {
    kind = "warn";
    text = t("detached.verdict.unverified");
    icon = <AlertTriangle size={11} />;
  }
  const style = VERDICT_STYLE[kind];
  return (
    <span
      className="flex items-center gap-1"
      style={{
        ...style,
        fontSize: 10.5,
        fontWeight: 500,
        padding: "2px 7px",
        borderRadius: 4,
        alignSelf: "flex-start",
      }}
    >
      {icon}
      {text}
    </span>
  );
};

// ── Sign-in-Studio dialog ─────────────────────────────────────────────────────

const SIGNABLE_KINDS = new Set(["openpgp", "self_signed", "pkcs12"]);

type SignDialogProps = {
  projectId: string;
  docId: string;
  slotId: string;
  personName: string | null;
  onClose: () => void;
};

const SignDialog = ({
  projectId,
  docId,
  slotId,
  personName,
  onClose,
}: SignDialogProps) => {
  const { t } = useTranslation("signatureStamper");
  const { data: identities } = useSigningIdentities();
  const sign = useSignDetachedInStudio();
  const generate = useGenerateOpenPgpKey();
  const keys = (identities ?? []).filter((i) => SIGNABLE_KINDS.has(i.kind));
  const [mode, setMode] = useState<"pick" | "create">("pick");
  const [identityId, setIdentityId] = useState("");
  const [passphrase, setPassphrase] = useState("");
  const [name, setName] = useState(personName ?? "");
  const [email, setEmail] = useState("");
  const [newPass, setNewPass] = useState("");

  const effectiveMode = keys.length === 0 ? "create" : mode;
  const selected: SigningIdentity | undefined =
    keys.find((k) => k.id === identityId) ?? keys[0];
  const busy = sign.isPending || generate.isPending;

  const runSign = (id: string, pass: string) => {
    sign.mutate(
      { projectId, docId, slotId, identityId: id, passphrase: pass },
      {
        onSuccess: () => {
          toast.success(t("detached.slot.attachedToast"));
          onClose();
        },
        onError: (err) => toast.error(err.message),
      },
    );
  };

  const submit = () => {
    if (effectiveMode === "create") {
      generate.mutate(
        { name: name.trim(), email: email.trim(), passphrase: newPass },
        {
          onSuccess: (identity) => {
            runSign(identity.id, newPass);
          },
          onError: (err) => toast.error(err.message),
        },
      );
      return;
    }
    if (selected) runSign(selected.id, passphrase);
  };

  const canSubmit =
    effectiveMode === "create"
      ? name.trim().length > 0
      : selected !== undefined && (!selected.protected || passphrase !== "");

  return (
    <Modal
      isOpen
      onClose={onClose}
      width={460}
      title={t("detached.sign.title")}
      footer={
        <>
          <button
            type="button"
            className="btn"
            onClick={onClose}
            disabled={busy}
          >
            {t("detached.sign.cancel")}
          </button>
          <button
            type="button"
            className="btn btn-primary"
            onClick={submit}
            disabled={busy || !canSubmit}
          >
            {busy ? (
              <Spinner size="sm" />
            ) : effectiveMode === "create" ? (
              t("detached.sign.createAndSign")
            ) : (
              t("detached.sign.submit")
            )}
          </button>
        </>
      }
    >
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {effectiveMode === "pick" && selected && (
          <>
            <label style={{ fontSize: 12, fontWeight: 500 }}>
              {t("detached.sign.key")}
            </label>
            <select
              className="input"
              value={selected.id}
              onChange={(e) => {
                setIdentityId(e.target.value);
              }}
              style={{ fontSize: 13 }}
            >
              {keys.map((k) => (
                <option key={k.id} value={k.id}>
                  {k.label} ({t(`detached.sign.kind.${k.kind}`)})
                </option>
              ))}
            </select>
            {selected.protected && (
              <>
                <label style={{ fontSize: 12, fontWeight: 500 }}>
                  {t("detached.sign.passphrase")}
                </label>
                <input
                  className="input"
                  type="password"
                  autoFocus
                  value={passphrase}
                  onChange={(e) => {
                    setPassphrase(e.target.value);
                  }}
                  style={{ fontSize: 13 }}
                />
              </>
            )}
            <button
              type="button"
              className="btn xs ghost"
              style={{ alignSelf: "flex-start" }}
              onClick={() => {
                setMode("create");
              }}
            >
              <KeyRound size={10} />
              {t("detached.sign.newKey")}
            </button>
          </>
        )}
        {effectiveMode === "create" && (
          <>
            {keys.length === 0 && (
              <div
                style={{ fontSize: 12, color: "var(--fg-2)", lineHeight: 1.5 }}
              >
                {t("detached.sign.noKeys")}
              </div>
            )}
            <label style={{ fontSize: 12, fontWeight: 500 }}>
              {t("detached.sign.name")}
            </label>
            <input
              className="input"
              value={name}
              onChange={(e) => {
                setName(e.target.value);
              }}
              style={{ fontSize: 13 }}
            />
            <label style={{ fontSize: 12, fontWeight: 500 }}>
              {t("detached.sign.email")}
            </label>
            <input
              className="input"
              type="email"
              value={email}
              onChange={(e) => {
                setEmail(e.target.value);
              }}
              style={{ fontSize: 13 }}
            />
            <label style={{ fontSize: 12, fontWeight: 500 }}>
              {t("detached.sign.passphraseOptional")}
            </label>
            <input
              className="input"
              type="password"
              value={newPass}
              onChange={(e) => {
                setNewPass(e.target.value);
              }}
              style={{ fontSize: 13 }}
            />
            {keys.length > 0 && (
              <button
                type="button"
                className="btn xs ghost"
                style={{ alignSelf: "flex-start" }}
                onClick={() => {
                  setMode("pick");
                }}
              >
                {t("detached.sign.existing")}
              </button>
            )}
          </>
        )}
        <div style={{ fontSize: 11, color: "var(--fg-3)", lineHeight: 1.5 }}>
          {t("detached.sign.gostNote")}
        </div>
      </div>
    </Modal>
  );
};

// ── Per-slot signature row ────────────────────────────────────────────────────

export type SlotDetachedSignatureProps = {
  projectId: string;
  docId: string;
  slotId: string;
  label: string;
  personName: string | null;
  frozen: FrozenPdfResponse | undefined;
  signature: DetachedSignatureResponse | undefined;
};

const Field = ({ name, value }: { name: string; value: React.ReactNode }) => (
  <div className="flex" style={{ gap: 6, fontSize: 10.5 }}>
    <span className="dim shrink-0" style={{ minWidth: 70 }}>
      {name}
    </span>
    <span style={{ color: "var(--fg-1)", wordBreak: "break-word" }}>
      {value}
    </span>
  </div>
);

export const SlotDetachedSignature = ({
  projectId,
  docId,
  slotId,
  label,
  personName,
  frozen,
  signature,
}: SlotDetachedSignatureProps) => {
  const { t } = useTranslation("signatureStamper");
  const attach = useAttachDetachedSignature();
  const recheck = useRecheckDetachedSignature();
  const remove = useDeleteDetachedSignature();
  const completeChain = useCompleteChain();
  const trustRoot = useTrustRoot();
  const [signOpen, setSignOpen] = useState(false);
  const [cryptoProOpen, setCryptoProOpen] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const keyRef = useRef<HTMLInputElement>(null);
  const busy =
    attach.isPending ||
    recheck.isPending ||
    remove.isPending ||
    completeChain.isPending ||
    trustRoot.isPending;

  const upload = (file: File) => {
    attach.mutate(
      { projectId, docId, slotId, file },
      {
        onSuccess: () => {
          toast.success(t("detached.slot.attachedToast"));
        },
        onError: (err) => toast.error(err.message),
      },
    );
  };

  const addPublicKey = (file: File) => {
    recheck.mutate(
      { projectId, docId, slotId, publicKey: file },
      { onError: (err) => toast.error(err.message) },
    );
  };

  const handleDelete = () => {
    if (!window.confirm(t("detached.slot.deleteConfirm", { label }))) return;
    remove.mutate(
      { projectId, docId, slotId },
      { onError: (err) => toast.error(err.message) },
    );
  };

  const cryptoProDialog = cryptoProOpen && (
    <CryptoProSignDialog
      projectId={projectId}
      docId={docId}
      slotId={slotId}
      onClose={() => {
        setCryptoProOpen(false);
      }}
    />
  );

  if (!frozen) {
    return (
      <div
        style={{
          marginLeft: 42,
          display: "flex",
          flexDirection: "column",
          gap: 6,
          fontSize: 10.5,
          color: "var(--fg-2)",
        }}
      >
        <span>{t("detached.slot.needFreeze")}</span>
        <div>
          <button
            type="button"
            className="btn xs"
            onClick={() => {
              setCryptoProOpen(true);
            }}
            title={t("detached.cryptopro.buttonTitle")}
          >
            <KeyRound size={10} />
            {t("detached.cryptopro.button")}
          </button>
        </div>
        {cryptoProDialog}
      </div>
    );
  }

  const stale = frozen.stale;
  const current = signature?.current ?? true;

  return (
    <div
      style={{
        marginLeft: 42,
        display: "flex",
        flexDirection: "column",
        gap: 6,
        padding: dragOver ? 6 : 0,
        borderRadius: 6,
        border: dragOver ? "1px dashed var(--accent)" : "1px solid transparent",
      }}
      onDragOver={(e) => {
        if (stale) return;
        e.preventDefault();
        setDragOver(true);
      }}
      onDragLeave={() => {
        setDragOver(false);
      }}
      onDrop={(e) => {
        e.preventDefault();
        setDragOver(false);
        const file = e.dataTransfer.files.item(0);
        if (file && !stale) upload(file);
      }}
    >
      <input
        ref={fileRef}
        type="file"
        accept=".asc,.sig,.p7s,.p7m,.gpg,.pgp"
        style={{ display: "none" }}
        onChange={(e) => {
          const file = e.target.files?.[0];
          e.target.value = "";
          if (file) upload(file);
        }}
      />
      <input
        ref={keyRef}
        type="file"
        accept=".asc,.gpg,.pgp,.key"
        style={{ display: "none" }}
        onChange={(e) => {
          const file = e.target.files?.[0];
          e.target.value = "";
          if (file) addPublicKey(file);
        }}
      />

      {signature && (
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: 4,
            padding: "8px 10px",
            borderRadius: 6,
            border: "1px solid var(--border)",
            background: "var(--bg-0)",
          }}
        >
          <VerdictBadge
            verdict={signature.verdict}
            current={current}
            stale={stale}
          />
          {signature.verdict === "unknown_key" ? (
            <div
              style={{ fontSize: 10.5, color: "var(--fg-1)", lineHeight: 1.45 }}
            >
              {t("detached.slot.unknownKey", { keyId: signature.signer_id })}
            </div>
          ) : (
            <>
              <Field
                name={t("detached.field.signer")}
                value={signature.signer || "-"}
              />
              {signature.issuer && (
                <Field
                  name={t("detached.field.issuer")}
                  value={signature.issuer}
                />
              )}
              <Field
                name={t("detached.field.format")}
                value={`${t(`detached.format.${signature.format}`)}${
                  signature.format === "cms" && signature.algorithm
                    ? `, ${prettyAlgorithm(signature.algorithm)}`
                    : ""
                }`}
              />
              {signature.signed_at && (
                <Field
                  name={t("detached.field.signedAt")}
                  value={formatDateTime(signature.signed_at)}
                />
              )}
              {signature.not_after && (
                <Field
                  name={t("detached.field.validUntil")}
                  value={formatDate(signature.not_after)}
                />
              )}
              <Field
                name={t("detached.field.origin")}
                value={t(`detached.origin.${signature.origin}`)}
              />
            </>
          )}
          {signature.notes.length > 0 && (
            <ul
              style={{
                margin: "2px 0 0",
                paddingLeft: 14,
                fontSize: 10,
                color: "var(--fg-2)",
                lineHeight: 1.45,
              }}
            >
              {signature.notes.map((code) => {
                const [key = code, ...rest] = code.split(":");
                return (
                  <li key={code}>
                    {t(`detached.note.${key}`, {
                      reason: rest.join(":"),
                      defaultValue: code,
                    })}
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      )}

      {signature?.format === "cms" &&
        signature.notes.includes("chain_incomplete") && (
          <div>
            <button
              type="button"
              className="btn xs"
              disabled={busy}
              title={t("detached.chain.completeTitle")}
              onClick={() => {
                completeChain.mutate(
                  { projectId, docId, slotId },
                  { onError: (err) => toast.error(err.message) },
                );
              }}
            >
              {completeChain.isPending ? (
                <Spinner size="sm" />
              ) : (
                <Link2 size={10} />
              )}
              {t("detached.chain.complete")}
            </button>
          </div>
        )}
      {signature?.root_fingerprint && (
        <div
          style={{
            padding: "6px 8px",
            borderRadius: 6,
            border: "1px solid var(--border)",
            fontSize: 10.5,
            lineHeight: 1.5,
          }}
        >
          <div>
            {t("detached.chain.root", { subject: signature.root_subject })}
          </div>
          <div className="mono dim" style={{ wordBreak: "break-all" }}>
            SHA-256: {signature.root_fingerprint}
          </div>
          <button
            type="button"
            className="btn xs"
            style={{ marginTop: 4 }}
            disabled={busy}
            onClick={() => {
              if (
                !window.confirm(
                  t("detached.chain.trustConfirm", {
                    subject: signature.root_subject,
                    fingerprint: signature.root_fingerprint,
                  }),
                )
              )
                return;
              trustRoot.mutate(
                {
                  projectId,
                  docId,
                  slotId,
                  fingerprint: signature.root_fingerprint,
                },
                { onError: (err) => toast.error(err.message) },
              );
            }}
          >
            <ShieldCheck size={10} />
            {t("detached.chain.trust")}
          </button>
        </div>
      )}

      <div className="flex items-center" style={{ gap: 6, flexWrap: "wrap" }}>
        {!signature && (
          <>
            <button
              type="button"
              className="btn xs"
              disabled={busy || stale}
              onClick={() => fileRef.current?.click()}
              title={t("detached.slot.uploadTitle")}
            >
              {attach.isPending ? <Spinner size="sm" /> : <FileUp size={10} />}
              {t("detached.slot.upload")}
            </button>
            <button
              type="button"
              className="btn xs"
              disabled={busy || stale}
              onClick={() => {
                setSignOpen(true);
              }}
            >
              <PenLine size={10} />
              {t("detached.slot.signHere")}
            </button>
            <button
              type="button"
              className="btn xs"
              disabled={busy || stale}
              onClick={() => {
                setCryptoProOpen(true);
              }}
              title={t("detached.cryptopro.buttonTitle")}
            >
              <KeyRound size={10} />
              {t("detached.cryptopro.button")}
            </button>
          </>
        )}
        {signature?.verdict === "unknown_key" && (
          <button
            type="button"
            className="btn xs"
            disabled={busy}
            onClick={() => keyRef.current?.click()}
          >
            {recheck.isPending ? <Spinner size="sm" /> : <FileKey size={10} />}
            {t("detached.slot.addKey")}
          </button>
        )}
        {signature && (
          <>
            <button
              type="button"
              className="btn xs ghost"
              disabled={busy}
              onClick={() => {
                downloadUrl(
                  signatureDownloadUrls.detachedFile(projectId, docId, slotId),
                );
              }}
              title={t("detached.slot.download")}
            >
              <Download size={10} />
            </button>
            <button
              type="button"
              className="btn xs ghost"
              disabled={busy || stale}
              onClick={() => fileRef.current?.click()}
              title={t("detached.slot.replace")}
            >
              <FileUp size={10} />
            </button>
            <button
              type="button"
              className="btn xs ghost"
              disabled={busy || stale}
              onClick={() => {
                recheck.mutate(
                  { projectId, docId, slotId },
                  { onError: (err) => toast.error(err.message) },
                );
              }}
              title={t("detached.slot.recheck")}
            >
              <RefreshCw size={10} />
            </button>
            <button
              type="button"
              className="btn xs ghost"
              disabled={busy}
              style={{ color: "var(--c-err)" }}
              onClick={handleDelete}
              title={t("detached.slot.delete")}
            >
              <Trash2 size={10} />
            </button>
          </>
        )}
      </div>
      {!signature && (
        <div style={{ fontSize: 10, color: "var(--fg-3)" }}>
          {t("detached.slot.drop")}
        </div>
      )}

      {cryptoProDialog}
      {signOpen && (
        <SignDialog
          projectId={projectId}
          docId={docId}
          slotId={slotId}
          personName={personName}
          onClose={() => {
            setSignOpen(false);
          }}
        />
      )}
    </div>
  );
};

// ── Signer for the plate ──────────────────────────────────────────────────────

export type SignerPlateEditorProps = {
  projectId: string;
  slotId: string;
  signer: SignerInfoResponse | null | undefined;
  personName: string | null;
};

const PLATE_KEY_KINDS = new Set(["openpgp", "self_signed", "pkcs12"]);

export const SignerPlateEditor = ({
  projectId,
  slotId,
  signer,
  personName,
}: SignerPlateEditorProps) => {
  const { t } = useTranslation("signatureStamper");
  const setSigner = useSetSlotSigner();
  const clearSigner = useClearSlotSigner();
  const setLevel = useSetSignerLevel();
  const { data: identities } = useSigningIdentities();
  const fileRef = useRef<HTMLInputElement>(null);
  const [manual, setManual] = useState(false);
  const [owner, setOwner] = useState(personName ?? "");
  const [certId, setCertId] = useState("");
  const [validTo, setValidTo] = useState("");
  const keys = (identities ?? []).filter((i) => PLATE_KEY_KINDS.has(i.kind));
  const busy = setSigner.isPending || clearSigner.isPending;
  const onError = (err: Error) => toast.error(err.message);

  return (
    <div
      style={{
        marginLeft: 42,
        display: "flex",
        flexDirection: "column",
        gap: 6,
        fontSize: 10.5,
      }}
    >
      <input
        ref={fileRef}
        type="file"
        accept=".cer,.crt,.pem,.der,.asc,.gpg,.pgp"
        style={{ display: "none" }}
        onChange={(e) => {
          const file = e.target.files?.[0];
          e.target.value = "";
          if (file) setSigner.mutate({ projectId, slotId, file }, { onError });
        }}
      />
      <div className="flex items-center gap-1" style={{ color: "var(--fg-2)" }}>
        <span>{t("detached.plate.title")}</span>
      </div>
      {signer ? (
        <div
          style={{
            padding: "6px 8px",
            borderRadius: 6,
            border: "1px solid var(--border)",
            background: "var(--bg-0)",
            lineHeight: 1.5,
          }}
        >
          <div style={{ color: "var(--fg-0)", fontWeight: 500 }}>
            {signer.owner || "-"}
          </div>
          {signer.cert_id && (
            <div className="mono dim" style={{ wordBreak: "break-all" }}>
              {t(
                signer.kind === "openpgp"
                  ? "detached.plate.key"
                  : "detached.plate.certificate",
              )}
              : {signer.cert_id}
            </div>
          )}
          {signer.valid_to && (
            <div className="dim">
              {t("detached.plate.validUntil")}: {formatDate(signer.valid_to)}
            </div>
          )}
        </div>
      ) : (
        <div style={{ color: "var(--fg-3)", lineHeight: 1.45 }}>
          {t("detached.plate.empty")}
        </div>
      )}
      <div className="flex items-center" style={{ gap: 6, flexWrap: "wrap" }}>
        <button
          type="button"
          className="btn xs"
          disabled={busy}
          onClick={() => fileRef.current?.click()}
          title={t("detached.plate.fromFileTitle")}
        >
          {setSigner.isPending ? <Spinner size="sm" /> : <FileKey size={10} />}
          {t("detached.plate.fromFile")}
        </button>
        {keys.length > 0 && (
          <select
            className="input"
            value=""
            disabled={busy}
            onChange={(e) => {
              if (e.target.value) {
                setSigner.mutate(
                  { projectId, slotId, identityId: e.target.value },
                  { onError },
                );
              }
            }}
            style={{ height: 22, fontSize: 10.5, padding: "0 4px" }}
          >
            <option value="">{t("detached.plate.myKey")}</option>
            {keys.map((k) => (
              <option key={k.id} value={k.id}>
                {k.label}
              </option>
            ))}
          </select>
        )}
        <button
          type="button"
          className="btn xs ghost"
          disabled={busy}
          onClick={() => {
            setManual((v) => !v);
          }}
        >
          {t("detached.plate.manual")}
        </button>
        {signer && (
          <button
            type="button"
            className="btn xs ghost"
            disabled={busy}
            style={{ color: "var(--c-err)" }}
            onClick={() => {
              clearSigner.mutate({ projectId, slotId }, { onError });
            }}
            title={t("detached.plate.clear")}
          >
            <Trash2 size={10} />
          </button>
        )}
      </div>
      <label className="flex items-center" style={{ gap: 6 }}>
        <span className="dim">{t("detached.plate.level")}</span>
        <select
          className="input"
          value={signer?.level ?? ""}
          disabled={busy || setLevel.isPending}
          onChange={(e) => {
            setLevel.mutate(
              { projectId, slotId, level: e.target.value },
              { onError },
            );
          }}
          style={{ height: 22, fontSize: 10.5, padding: "0 4px" }}
        >
          <option value="">{t("detached.plate.levelNone")}</option>
          <option value="ukep">{t("detached.plate.levelUkep")}</option>
          <option value="unep">{t("detached.plate.levelUnep")}</option>
        </select>
      </label>
      {manual && (
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <input
            className="input"
            placeholder={t("detached.plate.ownerPlaceholder")}
            value={owner}
            onChange={(e) => {
              setOwner(e.target.value);
            }}
            style={{ height: 24, fontSize: 11 }}
          />
          <input
            className="input"
            placeholder={t("detached.plate.certPlaceholder")}
            value={certId}
            onChange={(e) => {
              setCertId(e.target.value);
            }}
            style={{ height: 24, fontSize: 11 }}
          />
          <label className="flex items-center" style={{ gap: 6 }}>
            <span className="dim">{t("detached.plate.validUntil")}</span>
            <input
              type="date"
              className="input"
              value={validTo}
              onChange={(e) => {
                setValidTo(e.target.value);
              }}
              style={{ height: 22, fontSize: 10.5, padding: "0 6px" }}
            />
          </label>
          <div>
            <button
              type="button"
              className="btn xs"
              disabled={busy || owner.trim() === ""}
              onClick={() => {
                setSigner.mutate(
                  {
                    projectId,
                    slotId,
                    owner,
                    certId,
                    validTo: validTo || null,
                  },
                  {
                    onSuccess: () => {
                      setManual(false);
                    },
                    onError,
                  },
                );
              }}
            >
              {t("detached.plate.apply")}
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
