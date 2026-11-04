import { useRef, useState } from "react";
import { FileUp, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  useAddTrustedRoot,
  useDeleteTrustedRoot,
  useGenerateOpenPgpKey,
  useImportOpenPgpKey,
  useOpenPgpKeys,
  useTrustedRoots,
} from "@entities/signing-identity";
import { useBootstrap } from "@entities/session";
import { localeTag, toast } from "@shared/lib";
import { Spinner } from "@shared/ui/Spinner";
import { formatFingerprint } from "./formatFingerprint";

const fieldLabel = { fontSize: "0.75rem", fontWeight: 500 } as const;
const formStyle = {
  display: "flex",
  flexDirection: "column",
  gap: 10,
} as const;
const footerStyle = {
  display: "flex",
  gap: 8,
  justifyContent: "flex-end",
  marginTop: 4,
} as const;

const formatDate = (iso: string): string =>
  new Date(iso).toLocaleDateString(localeTag(), {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });

// ── OpenPGP: generate ─────────────────────────────────────────────────────────

export const OpenPgpCreateForm = ({ onClose }: { onClose: () => void }) => {
  const { t } = useTranslation("settings");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [pass, setPass] = useState("");
  const generate = useGenerateOpenPgpKey();

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    generate.mutate(
      { name: name.trim(), email: email.trim(), passphrase: pass },
      {
        onSuccess: () => {
          toast.success(t("signing.openpgp.createdToast"));
          onClose();
        },
        onError: (err) => toast.error(err.message),
      },
    );
  };

  return (
    <form onSubmit={handleSubmit} style={formStyle}>
      <div
        style={{
          fontSize: "0.71875rem",
          color: "var(--fg-2)",
          lineHeight: 1.5,
        }}
      >
        {t("signing.openpgp.createHint")}
      </div>
      <label style={fieldLabel}>{t("signing.openpgp.nameField")}</label>
      <input
        className="input"
        value={name}
        onChange={(e) => {
          setName(e.target.value);
        }}
        placeholder={t("signing.openpgp.namePlaceholder")}
        required
        style={{ fontSize: "0.8125rem" }}
      />
      <label style={fieldLabel}>{t("signing.openpgp.emailField")}</label>
      <input
        className="input"
        type="email"
        value={email}
        onChange={(e) => {
          setEmail(e.target.value);
        }}
        style={{ fontSize: "0.8125rem" }}
      />
      <label style={fieldLabel}>{t("signing.openpgp.passphraseField")}</label>
      <input
        className="input"
        type="password"
        value={pass}
        onChange={(e) => {
          setPass(e.target.value);
        }}
        style={{ fontSize: "0.8125rem" }}
      />
      <div
        style={{ fontSize: "0.6875rem", color: "var(--fg-3)", lineHeight: 1.5 }}
      >
        {t("signing.openpgp.passphraseHint")}
      </div>
      <div style={footerStyle}>
        <button type="button" className="btn btn-ghost" onClick={onClose}>
          {t("signing.cancel")}
        </button>
        <button
          type="submit"
          className="btn btn-primary"
          disabled={generate.isPending || name.trim() === ""}
        >
          {generate.isPending ? <Spinner size="sm" /> : t("signing.create")}
        </button>
      </div>
    </form>
  );
};

// ── OpenPGP: import ───────────────────────────────────────────────────────────

export const OpenPgpImportForm = ({ onClose }: { onClose: () => void }) => {
  const { t } = useTranslation("settings");
  const [file, setFile] = useState<File | null>(null);
  const [pass, setPass] = useState("");
  const importMut = useImportOpenPgpKey();
  const fileRef = useRef<HTMLInputElement>(null);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) return;
    importMut.mutate(
      { file, ...(pass ? { passphrase: pass } : {}) },
      {
        onSuccess: (res) => {
          toast.success(
            t("signing.openpgp.importedToast", {
              secret: res.identities.length,
              pub: res.public_keys.length,
            }),
          );
          onClose();
        },
        onError: (err) => toast.error(err.message),
      },
    );
  };

  return (
    <form onSubmit={handleSubmit} style={formStyle}>
      <div
        style={{
          fontSize: "0.71875rem",
          color: "var(--fg-2)",
          lineHeight: 1.5,
        }}
      >
        {t("signing.openpgp.importHint")}
      </div>
      <input
        ref={fileRef}
        type="file"
        accept=".asc,.gpg,.pgp,.key"
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
          gap: "0.5rem",
          padding: "0.4375rem 0.75rem",
          border: "1px dashed var(--border)",
          borderRadius: "0.375rem",
          background: file
            ? "color-mix(in oklch, var(--accent) 8%, var(--bg-1))"
            : "var(--bg-2)",
          color: file ? "var(--fg-0)" : "var(--fg-2)",
          cursor: "pointer",
          fontSize: "0.75rem",
          textAlign: "left",
        }}
      >
        <FileUp size="0.875rem" style={{ flexShrink: 0 }} />
        <span className="truncate">
          {file ? file.name : t("signing.openpgp.chooseKey")}
        </span>
      </button>
      <label style={fieldLabel}>{t("signing.openpgp.importPassField")}</label>
      <input
        className="input"
        type="password"
        value={pass}
        onChange={(e) => {
          setPass(e.target.value);
        }}
        style={{ fontSize: "0.8125rem" }}
      />
      <div style={footerStyle}>
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

// ── Status + known public keys ────────────────────────────────────────────────

export const OpenPgpStatus = () => {
  const { t } = useTranslation("settings");
  const { data } = useOpenPgpKeys();
  if (!data) return null;
  if (!data.available) {
    return (
      <p style={{ fontSize: "0.71875rem", color: "var(--c-warn)", margin: 0 }}>
        {t("signing.openpgp.noGpg")}
      </p>
    );
  }
  const publicKeys = data.keys.filter((k) => !k.has_secret);
  if (publicKeys.length === 0) return null;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
      <div style={{ fontSize: "0.75rem", fontWeight: 500 }}>
        {t("signing.openpgp.knownKeys")}
      </div>
      {publicKeys.map((k) => (
        <div
          key={k.fingerprint}
          style={{
            fontSize: "0.6875rem",
            color: "var(--fg-2)",
            lineHeight: 1.45,
          }}
        >
          <span style={{ color: "var(--fg-1)" }}>{k.uids[0] ?? k.key_id}</span>
          <span className="mono" style={{ marginLeft: "0.375rem" }}>
            {formatFingerprint(k.fingerprint.slice(-16))}
          </span>
        </div>
      ))}
    </div>
  );
};

// ── Trusted roots ─────────────────────────────────────────────────────────────

export const TrustedRootsBlock = () => {
  const { t } = useTranslation("settings");
  const { data: roots } = useTrustedRoots();
  const add = useAddTrustedRoot();
  const del = useDeleteTrustedRoot();
  const fileRef = useRef<HTMLInputElement>(null);
  const bootstrap = useBootstrap().data;
  // На сервере доверенные корни общие для установки: менять их может только админ (иначе 403).
  const readOnly =
    bootstrap?.mode === "server" && !bootstrap.capabilities.admin;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
      <div style={{ fontSize: "0.8125rem", fontWeight: 600 }}>
        {t("signing.roots.title")}
      </div>
      <div
        style={{
          fontSize: "0.71875rem",
          color: "var(--fg-2)",
          lineHeight: 1.5,
        }}
      >
        {t("signing.roots.hint")}
      </div>
      {(roots ?? []).map((r) => (
        <div
          key={r.fingerprint}
          style={{
            display: "flex",
            alignItems: "center",
            gap: "0.625rem",
            padding: "0.375rem 0.625rem",
            borderRadius: "0.375rem",
            border: "1px solid var(--border)",
            background: "var(--bg-2)",
          }}
        >
          <div style={{ flex: 1, minWidth: 0 }}>
            <div className="truncate" style={{ fontSize: "0.78125rem" }}>
              {r.subject || r.fingerprint.slice(0, 16)}
            </div>
            <div style={{ fontSize: "0.65625rem", color: "var(--fg-2)" }}>
              {t("signing.validUntil")}
              {formatDate(r.not_after)}
            </div>
          </div>
          {!readOnly && (
            <button
              className="btn btn-ghost icon"
              disabled={del.isPending}
              title={t("signing.delete")}
              style={{ padding: "0.25rem", color: "var(--fg-2)" }}
              onClick={() => {
                del.mutate(r.fingerprint, {
                  onError: (err) => toast.error(err.message),
                });
              }}
            >
              <Trash2 size="0.875rem" />
            </button>
          )}
        </div>
      ))}
      {readOnly && (
        <div style={{ fontSize: "0.71875rem", color: "var(--fg-2)" }}>
          {t("signing.roots.adminOnly")}
        </div>
      )}
      {!readOnly && (
        <input
          ref={fileRef}
          type="file"
          accept=".cer,.crt,.pem,.der"
          style={{ display: "none" }}
          onChange={(e) => {
            const file = e.target.files?.[0];
            e.target.value = "";
            if (!file) return;
            add.mutate(file, {
              onSuccess: () => {
                toast.success(t("signing.roots.addedToast"));
              },
              onError: (err) => toast.error(err.message),
            });
          }}
        />
      )}
      {!readOnly && (
        <div>
          <button
            className="btn btn-secondary"
            style={{ fontSize: "0.75rem", gap: "0.375rem" }}
            disabled={add.isPending}
            onClick={() => fileRef.current?.click()}
          >
            {add.isPending ? <Spinner size="sm" /> : <FileUp size="0.875rem" />}
            {t("signing.roots.add")}
          </button>
        </div>
      )}
    </div>
  );
};
