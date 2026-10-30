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
        gap: 10,
        margin: "6px 12px",
        padding: "10px 12px",
        borderRadius: "var(--r-2)",
        border:
          "1px solid color-mix(in oklch, var(--c-warn) 40%, var(--border))",
        background: "var(--c-warn-soft)",
        fontSize: 12,
        lineHeight: 1.5,
      }}
    >
      <ServerOff
        size={14}
        aria-hidden="true"
        style={{ color: "var(--c-warn)", flexShrink: 0, marginTop: 2 }}
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
