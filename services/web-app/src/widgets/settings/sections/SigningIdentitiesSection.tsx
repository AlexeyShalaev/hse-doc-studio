import { useRef, useState } from "react";
import {
  FileUp,
  Plus,
  ShieldCheck,
  ShieldOff,
  Trash2,
  Upload,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  useSigningIdentities,
  useCreateSelfSigned,
  useImportPkcs12,
  useDeleteSigningIdentity,
  type SigningIdentity,
  type SigningIdentityKind,
} from "@entities/signing-identity";
import { Spinner } from "@shared/ui/Spinner";
import { localeTag, toast } from "@shared/lib";
import { SettingHead } from "./Setting";

const KIND_LABEL: Record<SigningIdentityKind, string> = {
  self_signed: "signing.kindSelfSigned",
  pkcs12: "signing.kindPkcs12",
  pkcs11: "signing.kindPkcs11",
};

const formatDate = (iso: string): string => {
  const d = new Date(iso);
  return d.toLocaleDateString(localeTag(), {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
};

const isExpired = (notAfter: string): boolean =>
  new Date(notAfter) < new Date();

// ── Self-signed creation form ─────────────────────────────────────────────────

type SelfSignedFormProps = {
  onClose: () => void;
};

const SelfSignedForm = ({ onClose }: SelfSignedFormProps) => {
  const { t } = useTranslation("settings");
  const [label, setLabel] = useState("");
  const [cn, setCn] = useState("");
  const [days, setDays] = useState(825);
  const create = useCreateSelfSigned();

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    create.mutate(
      { label, subject_cn: cn, validity_days: days },
      {
        onSuccess: () => {
          toast.success(t("signing.createdToast"));
          onClose();
        },
        onError: (err) => toast.error(String(err)),
      },
    );
  };

  return (
    <form
      onSubmit={handleSubmit}
      style={{ display: "flex", flexDirection: "column", gap: 10 }}
    >
      <label style={{ fontSize: 12, fontWeight: 500 }}>
        {t("signing.labelField")}
      </label>
      <input
        className="input"
        value={label}
        onChange={(e) => {
          setLabel(e.target.value);
        }}
        placeholder={t("signing.labelSelfSignedPlaceholder")}
        required
        style={{ fontSize: 13 }}
      />
      <label style={{ fontSize: 12, fontWeight: 500 }}>
        {t("signing.commonNameField")}
      </label>
      <input
        className="input"
        value={cn}
        onChange={(e) => {
          setCn(e.target.value);
        }}
        placeholder={t("signing.commonNamePlaceholder")}
        required
        style={{ fontSize: 13 }}
      />
      <label style={{ fontSize: 12, fontWeight: 500 }}>
        {t("signing.validityField")}
      </label>
      <input
        className="input"
        type="number"
        value={days}
        min={1}
        max={3650}
        onChange={(e) => {
          setDays(Number(e.target.value));
        }}
        style={{ fontSize: 13 }}
      />
      <div
        style={{
          display: "flex",
          gap: 8,
          justifyContent: "flex-end",
          marginTop: 4,
        }}
      >
        <button type="button" className="btn btn-ghost" onClick={onClose}>
          {t("signing.cancel")}
        </button>
        <button
          type="submit"
          className="btn btn-primary"
          disabled={create.isPending}
        >
          {create.isPending ? <Spinner size="sm" /> : t("signing.create")}
        </button>
      </div>
    </form>
  );
};

// ── PKCS#12 import form ───────────────────────────────────────────────────────

type Pkcs12FormProps = {
  onClose: () => void;
};

const Pkcs12Form = ({ onClose }: Pkcs12FormProps) => {
  const { t } = useTranslation("settings");
  const [label, setLabel] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [pass, setPass] = useState("");
  const importMut = useImportPkcs12();
  const fileRef = useRef<HTMLInputElement>(null);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) return;
    importMut.mutate(
      { label, file, ...(pass ? { passphrase: pass } : {}) },
      {
        onSuccess: () => {
          toast.success(t("signing.importedToast"));
          onClose();
        },
        onError: (err) => toast.error(String(err)),
      },
    );
  };

  return (
    <form
      onSubmit={handleSubmit}
      style={{ display: "flex", flexDirection: "column", gap: 10 }}
    >
      <label style={{ fontSize: 12, fontWeight: 500 }}>
        {t("signing.labelField")}
      </label>
      <input
        className="input"
        value={label}
        onChange={(e) => {
          setLabel(e.target.value);
        }}
        placeholder={t("signing.labelPkcs12Placeholder")}
        required
        style={{ fontSize: 13 }}
      />
      <label style={{ fontSize: 12, fontWeight: 500 }}>
        {t("signing.fileField")}
      </label>
      <input
        ref={fileRef}
        type="file"
        accept=".p12,.pfx"
        onChange={(e) => {
          setFile(e.target.files?.[0] ?? null);
        }}
        style={{ display: "none" }}
      />
      <button
        type="button"
        onClick={() => fileRef.current?.click()}
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          padding: "7px 12px",
          border: "1px dashed var(--border)",
          borderRadius: 6,
          background: file
            ? "color-mix(in oklch, var(--accent) 8%, var(--bg-1))"
            : "var(--bg-2)",
          color: file ? "var(--fg-0)" : "var(--fg-2)",
          cursor: "pointer",
          fontSize: 12,
          textAlign: "left",
          transition: "border-color 0.15s, background 0.15s",
        }}
      >
        <FileUp
          size={14}
          style={{
            flexShrink: 0,
            color: file ? "var(--accent)" : "var(--fg-3)",
          }}
        />
        <span className="truncate">
          {file ? file.name : t("signing.chooseFile")}
        </span>
        {file && (
          <span
            style={{
              marginLeft: "auto",
              fontSize: 10,
              color: "var(--fg-3)",
              flexShrink: 0,
            }}
          >
            {(file.size / 1024).toFixed(1)} KB
          </span>
        )}
      </button>
      <label style={{ fontSize: 12, fontWeight: 500 }}>
        {t("signing.passwordField")}
      </label>
      <input
        className="input"
        type="password"
        value={pass}
        onChange={(e) => {
          setPass(e.target.value);
        }}
        style={{ fontSize: 13 }}
      />
      <div
        style={{
          display: "flex",
          gap: 8,
          justifyContent: "flex-end",
          marginTop: 4,
        }}
      >
        <button type="button" className="btn btn-ghost" onClick={onClose}>
          {t("signing.cancel")}
        </button>
        <button
          type="submit"
          className="btn btn-primary"
          disabled={importMut.isPending || !file}
        >
          {importMut.isPending ? <Spinner size="sm" /> : t("signing.import")}
        </button>
      </div>
    </form>
  );
};

// ── Identity card ─────────────────────────────────────────────────────────────

type IdentityCardProps = {
  identity: SigningIdentity;
};

const IdentityCard = ({ identity }: IdentityCardProps) => {
  const { t } = useTranslation("settings");
  const del = useDeleteSigningIdentity();
  const expired = isExpired(identity.not_after);

  const handleDelete = () => {
    if (!confirm(t("signing.deleteConfirm", { label: identity.label }))) return;
    del.mutate(identity.id, {
      onSuccess: () => toast.success(t("signing.deletedToast")),
      onError: (err) => toast.error(String(err)),
    });
  };

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 10,
        padding: "8px 10px",
        borderRadius: 6,
        border: "1px solid var(--border)",
        background: "var(--bg-2)",
      }}
    >
      {identity.trusted ? (
        <ShieldCheck
          size={16}
          style={{ color: "var(--accent)", flexShrink: 0 }}
        />
      ) : (
        <ShieldOff size={16} style={{ color: "var(--fg-3)", flexShrink: 0 }} />
      )}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div
          style={{
            fontSize: 13,
            fontWeight: 500,
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          {identity.label}
        </div>
        <div style={{ fontSize: 11, color: "var(--fg-2)", marginTop: 2 }}>
          <span>{t(KIND_LABEL[identity.kind])}</span>
          <span style={{ margin: "0 5px" }}>·</span>
          <span>{identity.subject_cn}</span>
          <span style={{ margin: "0 5px" }}>·</span>
          <span style={{ color: expired ? "var(--warn)" : "var(--fg-2)" }}>
            {expired ? t("signing.expired") : t("signing.validUntil")}
            {formatDate(identity.not_after)}
          </span>
          {!identity.trusted && (
            <>
              <span style={{ margin: "0 5px" }}>·</span>
              <span style={{ color: "var(--fg-3)" }}>
                {t("signing.selfSigned")}
              </span>
            </>
          )}
        </div>
      </div>
      <button
        className="btn btn-ghost icon"
        onClick={handleDelete}
        disabled={del.isPending}
        title={t("signing.delete")}
        style={{ padding: 4, color: "var(--fg-2)" }}
      >
        {del.isPending ? <Spinner size="sm" /> : <Trash2 size={14} />}
      </button>
    </div>
  );
};

// ── Main section ──────────────────────────────────────────────────────────────

type Mode = "none" | "self-signed" | "pkcs12";

export const SigningIdentitiesSection = () => {
  const { t } = useTranslation("settings");
  const { data: identities, isLoading } = useSigningIdentities();
  const [mode, setMode] = useState<Mode>("none");

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <SettingHead
        anchorId="signing"
        title={t("signing.title")}
        sub={t("signing.subtitle")}
      />

      {isLoading ? (
        <Spinner size="sm" />
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {(identities ?? []).map((id) => (
            <IdentityCard key={id.id} identity={id} />
          ))}
          {(identities ?? []).length === 0 && (
            <p style={{ fontSize: 12, color: "var(--fg-3)", margin: 0 }}>
              {t("signing.loading")}
            </p>
          )}
        </div>
      )}

      {mode === "none" && (
        <div style={{ display: "flex", gap: 8 }}>
          <button
            className="btn btn-secondary"
            onClick={() => {
              setMode("self-signed");
            }}
            style={{ fontSize: 12, gap: 6 }}
          >
            <Plus size={14} />
            {t("signing.selfSigned")}
          </button>
          <button
            className="btn btn-secondary"
            onClick={() => {
              setMode("pkcs12");
            }}
            style={{ fontSize: 12, gap: 6 }}
          >
            <Upload size={14} />
            {t("signing.importP12")}
          </button>
        </div>
      )}

      {mode === "self-signed" && (
        <SelfSignedForm
          onClose={() => {
            setMode("none");
          }}
        />
      )}
      {mode === "pkcs12" && (
        <Pkcs12Form
          onClose={() => {
            setMode("none");
          }}
        />
      )}
    </div>
  );
};
