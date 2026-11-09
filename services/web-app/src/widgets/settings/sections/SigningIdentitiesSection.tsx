import { useRef, useState } from "react";
import {
  Download,
  FileUp,
  KeyRound,
  Plus,
  ShieldCheck,
  ShieldOff,
  Trash2,
  Upload,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  useSigningIdentities,
  useDefaultSigningKey,
  useSetDefaultSigningKey,
  useCreateSelfSigned,
  useImportPkcs12,
  useDeleteSigningIdentity,
  publicKeyUrl,
  type SigningIdentity,
  type SigningIdentityKind,
} from "@entities/signing-identity";
import { useBootstrap } from "@entities/session";
import { Spinner } from "@shared/ui/Spinner";
import { Notice } from "@shared/ui/ConflictKit";
import { localeTag, toast } from "@shared/lib";
import { SettingHead } from "./Setting";
import { formatFingerprint } from "./formatFingerprint";
import {
  OpenPgpCreateForm,
  OpenPgpImportForm,
  OpenPgpStatus,
  TrustedRootsBlock,
} from "./SigningExtras";

const KIND_LABEL: Record<SigningIdentityKind, string> = {
  self_signed: "signing.kindSelfSigned",
  pkcs12: "signing.kindPkcs12",
  pkcs11: "signing.kindPkcs11",
  openpgp: "signing.kindOpenpgp",
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
      style={{ display: "flex", flexDirection: "column", gap: "0.625rem" }}
    >
      <label style={{ fontSize: "0.75rem", fontWeight: 500 }}>
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
        style={{ fontSize: "0.8125rem" }}
      />
      <label style={{ fontSize: "0.75rem", fontWeight: 500 }}>
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
        style={{ fontSize: "0.8125rem" }}
      />
      <label style={{ fontSize: "0.75rem", fontWeight: 500 }}>
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
        style={{ fontSize: "0.8125rem" }}
      />
      <div
        style={{
          display: "flex",
          gap: "0.5rem",
          justifyContent: "flex-end",
          marginTop: "0.25rem",
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
      style={{ display: "flex", flexDirection: "column", gap: "0.625rem" }}
    >
      <label style={{ fontSize: "0.75rem", fontWeight: 500 }}>
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
        style={{ fontSize: "0.8125rem" }}
      />
      <label style={{ fontSize: "0.75rem", fontWeight: 500 }}>
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
          transition: "border-color 0.15s, background 0.15s",
        }}
      >
        <FileUp
          size="0.875rem"
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
              fontSize: "0.625rem",
              color: "var(--fg-3)",
              flexShrink: 0,
            }}
          >
            {(file.size / 1024).toFixed(1)} KB
          </span>
        )}
      </button>
      <label style={{ fontSize: "0.75rem", fontWeight: 500 }}>
        {t("signing.passwordField")}
      </label>
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
        style={{
          display: "flex",
          gap: "0.5rem",
          justifyContent: "flex-end",
          marginTop: "0.25rem",
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
        gap: "0.625rem",
        padding: "0.5rem 0.625rem",
        borderRadius: "0.375rem",
        border: "1px solid var(--border)",
        background: "var(--bg-2)",
      }}
    >
      {identity.trusted ? (
        <ShieldCheck
          size="1rem"
          style={{ color: "var(--accent)", flexShrink: 0 }}
        />
      ) : (
        <ShieldOff
          size="1rem"
          style={{ color: "var(--fg-3)", flexShrink: 0 }}
        />
      )}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div
          style={{
            fontSize: "0.8125rem",
            fontWeight: 500,
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          {identity.label}
        </div>
        <div
          style={{
            fontSize: "0.6875rem",
            color: "var(--fg-2)",
            marginTop: "0.125rem",
          }}
        >
          <span>{t(KIND_LABEL[identity.kind])}</span>
          <span style={{ margin: "0 0.3125rem" }}>·</span>
          <span>{identity.subject_cn}</span>
          <span style={{ margin: "0 0.3125rem" }}>·</span>
          <span style={{ color: expired ? "var(--warn)" : "var(--fg-2)" }}>
            {expired ? t("signing.expired") : t("signing.validUntil")}
            {formatDate(identity.not_after)}
          </span>
          {identity.kind === "openpgp" && identity.fingerprint && (
            <>
              <span style={{ margin: "0 0.3125rem" }}>·</span>
              <span className="mono" title={identity.fingerprint}>
                {formatFingerprint(identity.fingerprint.slice(-16))}
              </span>
              {identity.protected && (
                <span style={{ marginLeft: "0.375rem", color: "var(--fg-3)" }}>
                  {t("signing.openpgp.protected")}
                </span>
              )}
            </>
          )}
          {identity.kind !== "openpgp" && !identity.trusted && (
            <>
              <span style={{ margin: "0 0.3125rem" }}>·</span>
              <span style={{ color: "var(--fg-3)" }}>
                {t("signing.selfSigned")}
              </span>
            </>
          )}
        </div>
      </div>
      {identity.kind === "openpgp" && (
        <a
          className="btn btn-ghost icon"
          href={publicKeyUrl(identity.id)}
          title={t("signing.openpgp.exportPublic")}
          style={{ padding: "0.25rem", color: "var(--fg-2)" }}
        >
          <Download size="0.875rem" />
        </a>
      )}
      <button
        className="btn btn-ghost icon"
        onClick={handleDelete}
        disabled={del.isPending}
        title={t("signing.delete")}
        style={{ padding: "0.25rem", color: "var(--fg-2)" }}
      >
        {del.isPending ? <Spinner size="sm" /> : <Trash2 size="0.875rem" />}
      </button>
    </div>
  );
};

// ── Main section ──────────────────────────────────────────────────────────────

type Mode = "none" | "self-signed" | "pkcs12" | "openpgp" | "openpgp-import";

/**
 * Администратор запретил серверу хранить секретные ключи: вместо форм показываем пояснение
 * и пути без хранения. В локальном режиме политики нет.
 */
const SigningForbidden = () => {
  const { t } = useTranslation("settings");
  return (
    <div
      style={{ display: "flex", flexDirection: "column", gap: "1rem" }}
      data-testid="signing-forbidden"
    >
      <SettingHead
        anchorId="signing"
        title={t("signing.title")}
        sub={t("signing.subtitle")}
      />
      <Notice
        tone="info"
        text={`${t("signing.forbiddenTitle")}. ${t("signing.forbiddenBody")}`}
      />
      <div
        style={{ display: "flex", flexDirection: "column", gap: "0.375rem" }}
      >
        <strong style={{ fontSize: "0.78125rem" }}>
          {t("signing.forbiddenAltTitle")}
        </strong>
        <ul
          style={{
            margin: 0,
            paddingLeft: "1.125rem",
            fontSize: "0.75rem",
            lineHeight: 1.6,
            color: "var(--fg-2)",
          }}
        >
          <li>{t("signing.forbiddenAlt1")}</li>
          <li>{t("signing.forbiddenAlt2")}</li>
        </ul>
        <p
          style={{
            margin: "0.25rem 0 0",
            fontSize: "0.75rem",
            color: "var(--fg-2)",
          }}
        >
          {t("signing.forbiddenAsk")}
        </p>
      </div>
    </div>
  );
};

export const SigningIdentitiesSection = () => {
  const bootstrap = useBootstrap().data;
  // Только серверный режим: в локальном personal_signing_keys всегда ложно и ничего не значит.
  const forbidden =
    bootstrap?.mode === "server" &&
    !bootstrap.capabilities.personal_signing_keys;
  return forbidden ? <SigningForbidden /> : <SigningIdentitiesList />;
};

/**
 * Ключ по умолчанию: им «Подписать комплект» подписывает свои слоты, и из него
 * плашка открепленной ЭП берёт данные подписанта. Единственный ключ выбирается
 * сам. Пароль ключа Студия не хранит: его спрашивают при подписи.
 */
const DefaultKeySelect = ({
  identities,
}: {
  identities: readonly SigningIdentity[];
}) => {
  const { t } = useTranslation("settings");
  const { data } = useDefaultSigningKey();
  const { mutate, isPending } = useSetDefaultSigningKey();
  if (identities.length === 0) return null;
  return (
    <label style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
      <span style={{ fontSize: "0.75rem" }}>{t("signing.defaultKey")}</span>
      <select
        className="input"
        disabled={isPending}
        value={data?.identity_id ?? ""}
        onChange={(event) => {
          mutate(event.target.value === "" ? null : event.target.value);
        }}
      >
        <option value="">
          {data?.auto
            ? t("signing.defaultKeyAuto")
            : t("signing.defaultKeyNone")}
        </option>
        {identities.map((identity) => (
          <option key={identity.id} value={identity.id}>
            {identity.label}
          </option>
        ))}
      </select>
      <span style={{ fontSize: "0.6875rem", color: "var(--fg-3)" }}>
        {t("signing.defaultKeyHint")}
      </span>
    </label>
  );
};

const SigningIdentitiesList = () => {
  const { t } = useTranslation("settings");
  const { data: identities, isLoading } = useSigningIdentities();
  const [mode, setMode] = useState<Mode>("none");

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
      <SettingHead
        anchorId="signing"
        title={t("signing.title")}
        sub={t("signing.subtitle")}
      />

      {isLoading ? (
        <Spinner size="sm" />
      ) : (
        <div
          style={{ display: "flex", flexDirection: "column", gap: "0.375rem" }}
        >
          {(identities ?? []).map((id) => (
            <IdentityCard key={id.id} identity={id} />
          ))}
          {(identities ?? []).length === 0 && (
            <p style={{ fontSize: "0.75rem", color: "var(--fg-3)", margin: 0 }}>
              {t("signing.loading")}
            </p>
          )}
        </div>
      )}

      <DefaultKeySelect identities={identities ?? []} />

      <OpenPgpStatus />

      {mode === "none" && (
        <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
          <button
            className="btn btn-secondary"
            onClick={() => {
              setMode("openpgp");
            }}
            style={{ fontSize: "0.75rem", gap: "0.375rem" }}
          >
            <KeyRound size="0.875rem" />
            {t("signing.openpgp.create")}
          </button>
          <button
            className="btn btn-secondary"
            onClick={() => {
              setMode("openpgp-import");
            }}
            style={{ fontSize: "0.75rem", gap: "0.375rem" }}
          >
            <Upload size="0.875rem" />
            {t("signing.openpgp.import")}
          </button>
          <button
            className="btn btn-secondary"
            onClick={() => {
              setMode("self-signed");
            }}
            style={{ fontSize: "0.75rem", gap: "0.375rem" }}
          >
            <Plus size="0.875rem" />
            {t("signing.selfSigned")}
          </button>
          <button
            className="btn btn-secondary"
            onClick={() => {
              setMode("pkcs12");
            }}
            style={{ fontSize: "0.75rem", gap: "0.375rem" }}
          >
            <Upload size="0.875rem" />
            {t("signing.importP12")}
          </button>
        </div>
      )}

      {mode === "openpgp" && (
        <OpenPgpCreateForm
          onClose={() => {
            setMode("none");
          }}
        />
      )}
      {mode === "openpgp-import" && (
        <OpenPgpImportForm
          onClose={() => {
            setMode("none");
          }}
        />
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
      <TrustedRootsBlock />
    </div>
  );
};
