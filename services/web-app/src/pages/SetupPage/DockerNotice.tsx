import { useTranslation } from "react-i18next";
import { AlertTriangle, RefreshCw } from "lucide-react";
import { ManualCommand } from "./ManualCommand";

type DockerNoticeProps = {
  code: string;
  socketGid?: string | undefined;
  hostPath: string;
  isRechecking: boolean;
  onRecheck: () => void;
};

/**
 * Докер недоступен — мастер бессилен и честно об этом говорит.
 *
 * Настроить себя приложение может только через докера: примонтировать папку к
 * живому контейнеру нельзя, нужно его пересоздать. Поэтому вместо кнопки,
 * которая заведомо не сработает, показываем причину и готовую команду.
 */
export const DockerNotice = ({
  code,
  socketGid,
  hostPath,
  isRechecking,
  onRecheck,
}: DockerNoticeProps) => {
  const { t } = useTranslation("setup");

  return (
    <div>
      <div
        role="alert"
        style={{
          display: "flex",
          alignItems: "flex-start",
          gap: 10,
          padding: "12px 14px",
          borderRadius: 10,
          background: "var(--c-warn-soft)",
          border: "1px solid var(--c-warn)",
        }}
      >
        <AlertTriangle
          size={16}
          style={{ color: "var(--c-warn)", flexShrink: 0, marginTop: 1 }}
        />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontWeight: 600, color: "var(--c-warn)" }}>
            {t(`docker.${code}.title`, {
              defaultValue: t("docker.unknown.title"),
            })}
          </div>
          <div className="dim" style={{ fontSize: 12, marginTop: 3 }}>
            {t(`docker.${code}.hint`, {
              defaultValue: t("docker.unknown.hint"),
            })}
          </div>
        </div>
        <button
          type="button"
          className="btn xs"
          disabled={isRechecking}
          onClick={onRecheck}
          style={{ flexShrink: 0 }}
        >
          <RefreshCw size={11} />
          {t("docker.recheck")}
        </button>
      </div>
      <ManualCommand hostPath={hostPath} socketGid={socketGid} />
    </div>
  );
};
