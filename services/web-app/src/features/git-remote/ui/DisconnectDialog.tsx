import { useState } from "react";
import { Unplug } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { GitCredential } from "@entities/git-remote";
import {
  describeGitError,
  useDisconnectRemote,
  type GitRemoteInfo,
} from "@entities/git-sync";
import { toast } from "@shared/lib";
import { Modal } from "@shared/ui/Modal";
import { Notice } from "@shared/ui/ConflictKit";
import { Spinner } from "@shared/ui/Spinner";

export type DisconnectDialogProps = {
  isOpen: boolean;
  projectId: string;
  remote: GitRemoteInfo;
  /** Сколько версий ещё не отправлено: после отключения они останутся только здесь. */
  unsent: number;
  /** Доступ проекта с подробностями (какие проекты им пользуются); null, если неизвестен. */
  credential: GitCredential | null;
  onClose: () => void;
};

// Адрес без схемы читается легче: github.com/ivan/paper.
const repoName = (displayUrl: string): string =>
  displayUrl.replace(/^[a-z+]+:\/\//i, "").replace(/\.git$/i, "");

// Отключение не трогает ни локальную историю, ни сам репозиторий, поэтому окно
// спокойное. Единственное необратимое действие, удаление доступа, включается
// отдельной отметкой и недоступно, если доступ нужен другим проектам.
export const DisconnectDialog = ({
  isOpen,
  projectId,
  remote,
  unsent,
  credential,
  onClose,
}: DisconnectDialogProps) => {
  const { t } = useTranslation("gitRemote");
  const disconnect = useDisconnectRemote();
  const [forget, setForget] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const label = credential?.label ?? remote.credential?.label ?? null;
  const others = (credential?.used_by ?? []).filter(
    (project) => project.project_id !== projectId,
  );
  const canForget = label !== null && others.length === 0;

  const close = (): void => {
    if (disconnect.isPending) return;
    setForget(false);
    setError(null);
    onClose();
  };

  const confirm = (): void => {
    setError(null);
    disconnect.mutate(
      { projectId, forgetCredential: forget && canForget },
      {
        onSuccess: () => {
          toast.success(t("settings.disconnect.done"));
          setForget(false);
          onClose();
        },
        onError: (caught) => {
          setError(describeGitError(caught, t("settings.disconnect.failed")));
        },
      },
    );
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={close}
      width={460}
      title={t("settings.disconnect.title")}
      description={t("settings.disconnect.description", {
        repo: repoName(remote.display_url),
      })}
      footer={
        <>
          <button
            type="button"
            className="btn"
            onClick={close}
            disabled={disconnect.isPending}
          >
            {t("settings.disconnect.cancel")}
          </button>
          <button
            type="button"
            className="btn danger"
            onClick={confirm}
            disabled={disconnect.isPending}
          >
            {disconnect.isPending ? (
              <Spinner size="sm" />
            ) : (
              <Unplug size={12} aria-hidden="true" />
            )}
            {t("settings.disconnect.confirm")}
          </button>
        </>
      }
    >
      <div className="flex flex-col" style={{ gap: 12 }}>
        {unsent > 0 && (
          <Notice
            tone="warn"
            role="status"
            text={t("settings.disconnect.unsent", { count: unsent })}
          />
        )}

        {label !== null && (
          <div className="flex flex-col" style={{ gap: 6 }}>
            <label
              className="flex items-start"
              style={{
                gap: 8,
                cursor: canForget ? "pointer" : "not-allowed",
                opacity: canForget ? 1 : 0.6,
              }}
            >
              <input
                type="checkbox"
                checked={forget && canForget}
                disabled={!canForget || disconnect.isPending}
                onChange={(event) => {
                  setForget(event.target.checked);
                }}
                style={{ accentColor: "var(--accent)", marginTop: 3 }}
              />
              <span style={{ fontSize: 12.5 }}>
                {t("settings.disconnect.forget", { label })}
                <span
                  className="dim"
                  style={{ display: "block", fontSize: 11, marginTop: 2 }}
                >
                  {t("settings.disconnect.forgetHint")}
                </span>
              </span>
            </label>
            {!canForget && others.length > 0 && (
              <Notice
                tone="info"
                text={t("settings.disconnect.forgetBlocked", {
                  projects: others.map((project) => project.name).join(", "),
                })}
              />
            )}
          </div>
        )}

        {error !== null && <Notice tone="err" role="alert" text={error} />}
      </div>
    </Modal>
  );
};
