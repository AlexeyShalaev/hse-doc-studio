import { useTranslation } from "react-i18next";
import type { CloudListView } from "@entities/git-server";
import { Notice } from "@shared/ui/ConflictKit";

export type CloudNoticesProps = {
  view: CloudListView;
  /** Весь запрос не удался: не отвечает сама локальная Студия. */
  failed: boolean;
  retrying: boolean;
  onRetry: () => void;
  onReconnect: (serverUrl: string) => void;
};

/**
 * Что не так с облаком, одной строкой над списком: доступ истёк, сервер недоступен, список обрезан или пуст.
 * Проекты на этом компьютере при этом остаются на месте.
 */
export const CloudNotices = ({
  view,
  failed,
  retrying,
  onRetry,
  onReconnect,
}: CloudNoticesProps) => {
  const { t } = useTranslation("localStudio");
  const quiet =
    !failed &&
    view.problems.length === 0 &&
    view.truncated.length === 0 &&
    view.empty.length === 0;
  if (quiet) return null;
  const retry = (
    <button
      type="button"
      className="btn xs"
      onClick={onRetry}
      disabled={retrying}
      data-testid="cloud-retry"
    >
      {t("cloud.retry")}
    </button>
  );
  return (
    <div
      className="flex flex-col"
      style={{ gap: 8, marginBottom: 16 }}
      data-testid="cloud-notices"
    >
      {failed && (
        <Notice
          tone="warn"
          role="status"
          text={t("cloud.notice.failed")}
          action={retry}
        />
      )}
      {view.problems.map((server) =>
        server.state === "unreachable" ? (
          <Notice
            key={server.credential_id}
            tone="warn"
            role="status"
            text={t("cloud.notice.unreachable", { host: server.host })}
            action={retry}
          />
        ) : (
          <Notice
            key={server.credential_id}
            tone="warn"
            role="status"
            text={t(`cloud.notice.${server.state}`, { host: server.host })}
            action={
              <button
                type="button"
                className="btn xs"
                onClick={() => {
                  onReconnect(server.server_url);
                }}
                data-testid="cloud-reconnect"
              >
                {t("cloud.reconnect")}
              </button>
            }
          />
        ),
      )}
      {view.truncated.map((server) => (
        <Notice
          key={server.credential_id}
          tone="info"
          role="status"
          text={t("cloud.notice.truncated", {
            host: server.host,
            shown: server.projects.length,
            total: server.total,
          })}
        />
      ))}
      {view.empty.map((server) => (
        <Notice
          key={server.credential_id}
          tone="info"
          role="status"
          text={t("cloud.notice.empty", { host: server.host })}
        />
      ))}
    </div>
  );
};
