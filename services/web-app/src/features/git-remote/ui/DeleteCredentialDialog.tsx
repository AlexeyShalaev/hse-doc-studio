import { useState } from "react";
import { Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useDeleteCredential, type GitCredential } from "@entities/git-remote";
import { describeGitError, readGitError } from "@entities/git-sync";
import { toast } from "@shared/lib";
import { Modal } from "@shared/ui/Modal";
import { Notice } from "@shared/ui/ConflictKit";
import { Spinner } from "@shared/ui/Spinner";

export type DeleteCredentialDialogProps = {
  credential: GitCredential;
  onClose: () => void;
};

// Удаление доступа стирает токен или ключ без возврата. Если им пользуются
// проекты, окно называет их поимённо и просит подтвердить, что они останутся без
// доступа. Список берётся из карточки, но сервер может знать больше (проект
// подключили за это время): тогда он вернёт 409 со свежим списком, и окно
// покажет его и спросит ещё раз.
export const DeleteCredentialDialog = ({
  credential,
  onClose,
}: DeleteCredentialDialogProps) => {
  const { t } = useTranslation("gitAccess");
  const remove = useDeleteCredential();
  const [projects, setProjects] = useState(credential.used_by);
  const [error, setError] = useState<string | null>(null);
  const used = projects.length > 0;

  const close = (): void => {
    if (remove.isPending) return;
    onClose();
  };

  const confirm = (): void => {
    setError(null);
    remove.mutate(
      { id: credential.id, force: used },
      {
        onSuccess: () => {
          toast.success(t("access.credentials.deleteDialog.done"));
          onClose();
        },
        onError: (caught) => {
          const body = readGitError(caught);
          if (body?.code === "credential_in_use" && body.projects?.length) {
            setProjects(body.projects);
            return;
          }
          setError(
            describeGitError(
              caught,
              t("access.credentials.deleteDialog.failed"),
            ),
          );
        },
      },
    );
  };

  return (
    <Modal
      isOpen
      onClose={close}
      width={480}
      title={t("access.credentials.deleteDialog.title", {
        label: credential.label,
      })}
      description={t("access.credentials.deleteDialog.description")}
      footer={
        <>
          <button
            type="button"
            className="btn"
            onClick={close}
            disabled={remove.isPending}
          >
            {t("access.credentials.deleteDialog.cancel")}
          </button>
          <button
            type="button"
            className="btn danger"
            disabled={remove.isPending}
            onClick={confirm}
          >
            {remove.isPending ? (
              <Spinner size="sm" />
            ) : (
              <Trash2 size={12} aria-hidden="true" />
            )}
            {used
              ? t("access.credentials.deleteDialog.confirmUsed")
              : t("access.credentials.deleteDialog.confirm")}
          </button>
        </>
      }
    >
      <div className="flex flex-col" style={{ gap: 12 }}>
        {used ? (
          <div className="flex flex-col" style={{ gap: 8 }}>
            <Notice
              tone="warn"
              role="status"
              text={
                <>
                  <strong style={{ display: "block", fontWeight: 600 }}>
                    {t("access.credentials.deleteDialog.usedHeading")}
                  </strong>
                  {t("access.credentials.deleteDialog.usedText")}
                </>
              }
            />
            <ul
              aria-label={t("access.credentials.deleteDialog.usedHeading")}
              style={{
                margin: 0,
                padding: 0,
                listStyle: "none",
                display: "flex",
                flexDirection: "column",
                gap: 4,
              }}
            >
              {projects.map((project) => (
                <li
                  key={project.project_id}
                  className="truncate"
                  title={project.name}
                  style={{
                    padding: "6px 10px",
                    borderRadius: "var(--r-2)",
                    background: "var(--bg-2)",
                    fontSize: 12.5,
                  }}
                >
                  {project.name}
                </li>
              ))}
            </ul>
          </div>
        ) : (
          <p className="dim" style={{ margin: 0, fontSize: 12.5 }}>
            {t("access.credentials.deleteDialog.unused")}
          </p>
        )}
        {error !== null && <Notice tone="err" role="alert" text={error} />}
      </div>
    </Modal>
  );
};
