import { useId, useRef, useState } from "react";
import { Eye, EyeOff, FileArchive, Lock, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { formatFileSize } from "@shared/lib";
import { Notice } from "@shared/ui/ConflictKit";
import { FileDropZone, type FileDropZoneHandle } from "@shared/ui/FileDropZone";
import { isEncryptedBundleName } from "../../lib/cloneNames";

export type CloneBundleSourceProps = {
  file: File | null;
  onFileChange: (file: File | null) => void;
  password: string;
  onPasswordChange: (value: string) => void;
  /** Отказ, с которым вернули на шаг: файл повреждён, пароль не подошёл. */
  error: { code: string; message: string } | null;
};

const ACCEPT = ".bundle,.hseenc";

const isBundleName = (name: string): boolean => {
  const lower = name.toLowerCase();
  return lower.endsWith(".bundle") || lower.endsWith(".hseenc");
};

const PASSWORD_CODES = new Set([
  "bundle_password_required",
  "bundle_password_wrong",
]);

// Источник «Файл bundle»: перенос проекта без сети. Файл выбирается или
// перетаскивается, зашифрованный просит пароль. Содержимое файла до запуска
// клонирования не читается, поэтому карточки проекта здесь нет.
export const CloneBundleSource = ({
  file,
  onFileChange,
  password,
  onPasswordChange,
  error,
}: CloneBundleSourceProps) => {
  const { t } = useTranslation("gitRemote");
  const uid = useId();
  const zoneRef = useRef<FileDropZoneHandle>(null);
  const passwordId = `${uid}-password`;
  const hintId = `${uid}-password-hint`;
  const [showPassword, setShowPassword] = useState(false);
  const [wrongKind, setWrongKind] = useState(false);

  const accept = (picked: File): void => {
    setWrongKind(false);
    onFileChange(picked);
  };

  const encrypted = file !== null && isEncryptedBundleName(file.name);
  const passwordError =
    error !== null && PASSWORD_CODES.has(error.code) ? error.message : null;
  const fileError =
    error !== null && !PASSWORD_CODES.has(error.code) ? error.message : null;

  return (
    <div
      className="flex flex-col"
      style={{ gap: 14 }}
      data-testid="bundle-source"
    >
      <p className="dim" style={{ margin: 0, fontSize: 12.5, lineHeight: 1.5 }}>
        {t("clone.bundle.hint")}
      </p>

      <FileDropZone
        ref={zoneRef}
        showZone={file === null}
        accept={ACCEPT}
        isAcceptable={(picked) => isBundleName(picked.name)}
        onFile={accept}
        onReject={() => {
          setWrongKind(true);
        }}
        title={t("clone.bundle.drop")}
        action={t("clone.bundle.choose")}
        activeTitle={t("clone.bundle.dropActive")}
        hint={t("clone.bundle.accept")}
        inputLabel={t("clone.bundle.title")}
        testId="bundle-dropzone"
        inputTestId="bundle-input"
      />

      {file !== null && (
        <div
          className="card flex items-center"
          style={{ gap: 12, padding: "10px 12px" }}
          data-testid="bundle-file"
        >
          <span
            className="flex items-center justify-center"
            style={{
              width: 34,
              height: 34,
              borderRadius: "var(--r-2)",
              background: "var(--bg-2)",
              border: "1px solid var(--border)",
              color: "var(--fg-2)",
              flexShrink: 0,
            }}
          >
            {encrypted ? (
              <Lock size={16} aria-hidden="true" />
            ) : (
              <FileArchive size={16} aria-hidden="true" />
            )}
          </span>
          <span style={{ flex: 1, minWidth: 0 }}>
            <span
              className="mono truncate"
              style={{ display: "block", fontSize: 12.5, color: "var(--fg-0)" }}
              title={file.name}
            >
              {file.name}
            </span>
            <span className="dim" style={{ fontSize: 11.5 }}>
              {formatFileSize(file.size)}
              {encrypted && ` · ${t("clone.bundle.encrypted")}`}
            </span>
          </span>
          <button
            type="button"
            className="btn xs"
            onClick={() => {
              zoneRef.current?.open();
            }}
          >
            {t("clone.bundle.replace")}
          </button>
          <button
            type="button"
            className="btn xs ghost"
            aria-label={t("clone.bundle.remove")}
            title={t("clone.bundle.remove")}
            onClick={() => {
              onFileChange(null);
            }}
          >
            <X size={13} aria-hidden="true" />
          </button>
        </div>
      )}

      {wrongKind && (
        <Notice tone="err" role="alert" text={t("clone.bundle.wrongKind")} />
      )}
      {fileError && <Notice tone="err" role="alert" text={fileError} />}

      {encrypted && (
        <div className="field">
          <label htmlFor={passwordId}>{t("clone.bundle.password")}</label>
          <div className="flex" style={{ gap: 6 }}>
            <input
              id={passwordId}
              type={showPassword ? "text" : "password"}
              className="input"
              style={{ flex: 1, minWidth: 0 }}
              value={password}
              autoComplete="off"
              spellCheck={false}
              aria-invalid={passwordError !== null}
              aria-describedby={hintId}
              onChange={(event) => {
                onPasswordChange(event.target.value);
              }}
            />
            <button
              type="button"
              className="btn"
              aria-pressed={showPassword}
              aria-label={
                showPassword
                  ? t("clone.bundle.hidePassword")
                  : t("clone.bundle.showPassword")
              }
              onClick={() => {
                setShowPassword((current) => !current);
              }}
            >
              {showPassword ? (
                <EyeOff size={14} aria-hidden="true" />
              ) : (
                <Eye size={14} aria-hidden="true" />
              )}
            </button>
          </div>
          <div id={hintId}>
            {passwordError ? (
              <p
                className="text-xs"
                role="alert"
                style={{ margin: 0, color: "var(--c-err)" }}
              >
                {passwordError}
              </p>
            ) : (
              <p className="hint" style={{ margin: 0 }}>
                {t("clone.bundle.passwordHint")}
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
