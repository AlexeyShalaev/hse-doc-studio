import { useState } from "react";
import { KeyRound, TriangleAlert } from "lucide-react";
import { useTranslation } from "react-i18next";
import { CopyField } from "../CopyField";

// Секрет, который показывают один раз (токен, пароль, ключ). Закрыть панель
// можно сразу после копирования; если не копировали, просим подтвердить.

export type SecretOnceProps = {
  /** Что за секрет: «Токен раннера». */
  label: string;
  value: string;
  /** Пояснение под заголовком (куда вставить, что будет после закрытия). */
  hint?: string;
  /** Своё предупреждение вместо общего «Значение показано один раз…». */
  warning?: string;
  /** Что ещё скопировать до закрытия (команда запуска): стоит над «Готово». */
  extra?: React.ReactNode;
  onClose: () => void;
};

export const SecretOnce = ({
  label,
  value,
  hint,
  warning,
  extra,
  onClose,
}: SecretOnceProps) => {
  const { t } = useTranslation("uiPrimitives");
  const [copied, setCopied] = useState(false);
  const [confirming, setConfirming] = useState(false);

  const handleDone = (): void => {
    if (copied) onClose();
    else setConfirming(true);
  };

  return (
    <section
      aria-label={label}
      className="card"
      style={{
        padding: 16,
        borderColor: "color-mix(in oklch, var(--c-warn) 45%, transparent)",
        display: "flex",
        flexDirection: "column",
        gap: 12,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <KeyRound
          size={15}
          aria-hidden="true"
          style={{ color: "var(--c-warn)" }}
        />
        <strong style={{ fontSize: 13.5 }}>{label}</strong>
      </div>
      <p
        style={{
          margin: 0,
          fontSize: 12.5,
          color: "var(--fg-2)",
          lineHeight: 1.5,
        }}
      >
        {warning ?? t("secretOnce.warning")}
        {hint ? ` ${hint}` : ""}
      </p>
      <CopyField
        value={value}
        label={label}
        onCopied={() => {
          setCopied(true);
          setConfirming(false);
        }}
      />
      {extra}
      {confirming ? (
        <div
          role="alert"
          style={{
            display: "flex",
            flexDirection: "column",
            gap: 10,
            padding: 12,
            borderRadius: "var(--r-2)",
            background: "var(--c-warn-soft)",
            fontSize: 12.5,
          }}
        >
          <span style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
            <TriangleAlert
              size={14}
              aria-hidden="true"
              style={{ color: "var(--c-warn)", flexShrink: 0, marginTop: 1 }}
            />
            {t("secretOnce.notCopied")}
          </span>
          <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
            <button
              type="button"
              className="btn sm"
              onClick={() => {
                setConfirming(false);
              }}
            >
              {t("secretOnce.back")}
            </button>
            <button type="button" className="btn sm danger" onClick={onClose}>
              {t("secretOnce.closeAnyway")}
            </button>
          </div>
        </div>
      ) : (
        <div style={{ display: "flex", justifyContent: "flex-end" }}>
          <button type="button" className="btn primary" onClick={handleDone}>
            {t("secretOnce.done")}
          </button>
        </div>
      )}
    </section>
  );
};

SecretOnce.displayName = "SecretOnce";
