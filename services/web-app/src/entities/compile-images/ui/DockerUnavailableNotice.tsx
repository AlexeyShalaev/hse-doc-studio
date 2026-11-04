import { AlertTriangle, Copy } from "lucide-react";
import { useTranslation } from "react-i18next";
import { toast } from "@shared/lib";
import type { DockerStatus } from "../api/imagesApi";

// Коды приезжают из core/compile/docker_diagnosis.py. Незнакомый код (бэкенд
// новее фронта) осознанно падает в общий текст, а не ломает экран.
const SOCKET_PERMISSION = "socket_permission";

export type DockerUnavailableNoticeProps = {
  status: DockerStatus | undefined;
  /** Текст, когда причина неизвестна: у образов и у LanguageTool он свой. */
  fallbackDetail: string;
};

/**
 * Красный блок «Docker не доступен» с ПОЧИНКОЙ, а не с голым stderr.
 *
 * Самый частый отказ — нехватка прав на docker-сокет: процесс в контейнере
 * работает под непривилегированным пользователем, и без членства в группе
 * владельца сокета не собирается ни один документ. Починить это изнутри
 * контейнера нельзя (членство в группе задаётся при СОЗДАНИИ контейнера),
 * поэтому вместо кнопки «починить» даём точные две строки: gid читается с
 * самого сокета, так что команду остаётся только скопировать.
 */
export const DockerUnavailableNotice = ({
  status,
  fallbackDetail,
}: DockerUnavailableNoticeProps) => {
  const { t } = useTranslation("settings");
  const isPermission = status?.reason === SOCKET_PERMISSION;
  // 0 — владелец сокета на Docker Desktop; бэкенд читает gid с самого сокета,
  // так что подставленное число уже верно для этой машины.
  const gid = String(status?.socket_gid ?? 0);
  const fixCommand = `DOCKER_GID=${gid}\ndocker compose up -d`;

  const handleCopy = () => {
    void navigator.clipboard.writeText(fixCommand).then(() => {
      toast.success(t("images.dockerFixCopied"));
    });
  };

  return (
    <div
      className="flex items-start"
      style={{
        gap: "0.625rem",
        padding: "0.75rem",
        borderRadius: "0.375rem",
        border: "1px solid var(--c-err)",
        background: "var(--c-err-soft)",
      }}
    >
      <AlertTriangle
        size="0.875rem"
        style={{ color: "var(--c-err)", marginTop: 1, flexShrink: 0 }}
      />
      <div
        className="flex flex-col"
        style={{ gap: "0.375rem", minWidth: 0, flex: 1 }}
      >
        <div
          style={{
            fontSize: "0.78125rem",
            fontWeight: 600,
            color: "var(--c-err)",
          }}
        >
          {isPermission
            ? t("images.dockerPermissionTitle")
            : t("images.dockerUnavailable")}
        </div>
        <div className="dim" style={{ fontSize: "0.71875rem" }}>
          {isPermission
            ? t("images.dockerPermissionHint")
            : (status?.detail ?? fallbackDetail)}
        </div>

        {isPermission && (
          <>
            <div className="dim" style={{ fontSize: "0.71875rem" }}>
              {t("images.dockerPermissionSteps")}
            </div>
            <div
              className="flex items-center"
              style={{
                gap: "0.5rem",
                padding: "0.375rem 0.5rem",
                borderRadius: "0.25rem",
                background: "var(--c-bg)",
                border: "1px solid var(--c-border)",
              }}
            >
              <pre
                className="mono"
                style={{
                  fontSize: "0.6875rem",
                  margin: 0,
                  overflowX: "auto",
                  flex: 1,
                  minWidth: 0,
                }}
              >
                {fixCommand}
              </pre>
              <button
                type="button"
                className="btn ghost sm"
                onClick={handleCopy}
                title={t("images.dockerFixCopy")}
                style={{ flexShrink: 0 }}
              >
                <Copy size="0.75rem" />
                {t("images.dockerFixCopy")}
              </button>
            </div>
            {status.detail && (
              <details>
                <summary
                  className="dim"
                  style={{ fontSize: "0.6875rem", cursor: "pointer" }}
                >
                  {t("images.dockerRawError")}
                </summary>
                <pre
                  className="mono dim"
                  style={{
                    fontSize: "0.65625rem",
                    marginTop: "0.25rem",
                    whiteSpace: "pre-wrap",
                    wordBreak: "break-all",
                  }}
                >
                  {status.detail}
                </pre>
              </details>
            )}
          </>
        )}
      </div>
    </div>
  );
};
