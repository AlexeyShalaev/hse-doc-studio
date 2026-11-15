import { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  packErrorText,
  useCommitPack,
  type PackGit,
} from "@entities/pack-studio";
import { toast } from "@shared/lib";
import { Button, Modal, Textarea } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import { ChangedFiles } from "./ChangedFiles";

export type CommitDialogProps = {
  git: PackGit;
  isOpen: boolean;
  onClose: () => void;
  /** В редакторе есть несохранённая правка: в версию она не попадёт. */
  editorDirty: boolean;
};

/**
 * «Сохранить версию» (template-studio.md, 4.3): коммит правок на диске от профиля
 * человека. Пустое сообщение составляет сервер по соглашению conventional commits
 * (fix(packs) для patch, feat(packs) иначе); его можно заменить своим.
 */
export const CommitDialog = ({
  git,
  isOpen,
  onClose,
  editorDirty,
}: CommitDialogProps) => {
  const { t } = useTranslation("packStudio");
  const commit = useCommitPack(git.workspace.id);
  const [message, setMessage] = useState("");

  const close = () => {
    if (commit.isPending) return;
    commit.reset();
    setMessage("");
    onClose();
  };

  const submit = () => {
    const text = message.trim();
    commit.mutate(text === "" ? null : text, {
      onSuccess: (result) => {
        if (result.committed) {
          toast.success(
            t("git.commit.done", { sha: (result.sha ?? "").slice(0, 7) }),
          );
        } else {
          toast.info(t("git.commit.nothing"));
        }
        setMessage("");
        commit.reset();
        onClose();
      },
    });
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={close}
      title={t("git.commit.title")}
      description={
        git.branch
          ? t("git.commit.leadBranch", { branch: git.branch })
          : t("git.commit.leadNoBranch")
      }
      width={560}
      footer={
        <>
          <Button variant="secondary" onClick={close}>
            {t("common.cancel")}
          </Button>
          <Button
            disabled={commit.isPending || !git.dirty}
            onClick={submit}
            data-testid="git-commit-submit"
          >
            {t("git.commit.submit")}
          </Button>
        </>
      }
    >
      <div className="flex flex-col" style={{ gap: "0.75rem" }}>
        {editorDirty && (
          <Notice tone="warn" role="status" text={t("git.editorDirty")} />
        )}
        {git.dirty ? (
          <ChangedFiles files={git.uncommitted} testId="git-commit-files" />
        ) : (
          <p className="ps-pane-empty">{t("git.commit.nothing")}</p>
        )}
        <Textarea
          label={t("git.commit.message")}
          hint={t("git.commit.messageHint")}
          placeholder={t("git.commit.messagePlaceholder")}
          value={message}
          maxLength={2000}
          rows={3}
          onChange={(e) => {
            setMessage(e.target.value);
          }}
          isMono
          data-testid="git-commit-message"
        />
        {commit.isError && (
          <Notice tone="err" role="alert" text={packErrorText(commit.error)} />
        )}
      </div>
    </Modal>
  );
};
