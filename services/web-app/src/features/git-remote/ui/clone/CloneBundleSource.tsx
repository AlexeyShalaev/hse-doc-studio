import { useId, useRef, useState, type DragEvent } from "react";
import { Eye, EyeOff, FileArchive, Lock, UploadCloud, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Notice } from "@shared/ui/ConflictKit";
import { formatSize } from "../../lib/formatSize";
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
  const inputRef = useRef<HTMLInputElement>(null);
  const passwordId = `${uid}-password`;
  const hintId = `${uid}-password-hint`;
  const [dragging, setDragging] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [wrongKind, setWrongKind] = useState(false);

  const pick = (picked: File | null | undefined): void => {
    if (!picked) return;
    if (!isBundleName(picked.name)) {
      setWrongKind(true);
      return;
    }
    setWrongKind(false);
    onFileChange(picked);
  };

  const onDrop = (event: DragEvent<HTMLDivElement>): void => {
    event.preventDefault();
    setDragging(false);
    pick(event.dataTransfer.files[0]);
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

      <input
        ref={inputRef}
        type="file"
        accept={ACCEPT}
        hidden
        data-testid="bundle-input"
        aria-label={t("clone.bundle.title")}
        onChange={(event) => {
          pick(event.target.files?.[0]);
          // Тот же файл можно выбрать повторно.
          event.target.value = "";
        }}
      />

      {file === null ? (
        <div
          role="button"
          tabIndex={0}
          aria-label={`${t("clone.bundle.drop")} ${t("clone.bundle.choose")}`}
          data-testid="bundle-dropzone"
          onClick={() => inputRef.current?.click()}
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === " ") {
              event.preventDefault();
              inputRef.current?.click();
            }
          }}
          onDragOver={(event) => {
            event.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => {
            setDragging(false);
          }}
          onDrop={onDrop}
          className="flex flex-col items-center justify-center"
          style={{
            gap: 6,
            padding: "28px 16px",
            borderRadius: "var(--r-3)",
            border: `1.5px dashed ${dragging ? "var(--accent)" : "var(--border-strong)"}`,
            background: dragging ? "var(--accent-soft)" : "var(--bg-1)",
            cursor: "pointer",
            textAlign: "center",
            transition: "background 120ms, border-color 120ms",
          }}
        >
          <UploadCloud
            size={24}
            aria-hidden="true"
            style={{ color: dragging ? "var(--accent)" : "var(--fg-3)" }}
          />
          <span style={{ fontSize: 13, color: "var(--fg-0)" }}>
            {dragging ? (
              t("clone.bundle.dropActive")
            ) : (
              <>
                {t("clone.bundle.drop")}{" "}
                <span style={{ color: "var(--accent)", fontWeight: 500 }}>
                  {t("clone.bundle.choose")}
                </span>
              </>
            )}
          </span>
          <span className="dim" style={{ fontSize: 11.5 }}>
            {t("clone.bundle.accept")}
          </span>
        </div>
      ) : (
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
              {formatSize(file.size)}
              {encrypted && ` · ${t("clone.bundle.encrypted")}`}
            </span>
          </span>
          <button
            type="button"
            className="btn xs"
            onClick={() => inputRef.current?.click()}
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
