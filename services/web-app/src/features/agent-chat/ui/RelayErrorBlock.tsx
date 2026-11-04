import { ServerOff } from "lucide-react";
import { useTranslation } from "react-i18next";

export type RelayErrorBlockProps = {
  code: "relay_unavailable" | "relay_busy";
  /** Имя раннера выбранного провайдера, если оно известно. */
  runnerName: string | null;
  onPickModel: () => void;
};

/**
 * Ответ модели через свой раннер не пришёл: раннер не ответил или занят.
 * Блок говорит, что делать, и сразу открывает выбор другой модели.
 */
export const RelayErrorBlock = ({
  code,
  runnerName,
  onPickModel,
}: RelayErrorBlockProps) => {
  const { t } = useTranslation("agentChat");
  const text =
    code === "relay_busy"
      ? t("relayError.busy")
      : runnerName
        ? t("relayError.unavailable", { name: runnerName })
        : t("relayError.unavailableNoName");
  return (
    <div
      role="alert"
      data-testid="chat-relay-error"
      data-code={code}
      className="flex items-start"
      style={{
        gap: "0.625rem",
        margin: "0.375rem 0.75rem",
        padding: "0.625rem 0.75rem",
        borderRadius: "var(--r-2)",
        border:
          "1px solid color-mix(in oklch, var(--c-warn) 40%, var(--border))",
        background: "var(--c-warn-soft)",
        fontSize: "0.75rem",
        lineHeight: 1.5,
      }}
    >
      <ServerOff
        size="0.875rem"
        aria-hidden="true"
        style={{ color: "var(--c-warn)", flexShrink: 0, marginTop: "0.125rem" }}
      />
      <span style={{ flex: 1, minWidth: 0 }}>{text}</span>
      <button
        type="button"
        className="btn xs"
        onClick={onPickModel}
        data-testid="chat-relay-error-pick"
        style={{ flexShrink: 0 }}
      >
        {t("relayError.pick")}
      </button>
    </div>
  );
};
