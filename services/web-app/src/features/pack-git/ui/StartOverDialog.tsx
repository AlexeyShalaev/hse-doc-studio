import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  useStartPackOver,
  type PackGit,
  PackErrorText,
} from "@entities/pack-studio";
import { toast } from "@shared/lib";
import { Button, Modal } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";

export type StartOverDialogProps = {
  git: PackGit;
  /**
   * Слова окна. `classic` прежнее «Начать заново» (старый вид); `reset` «Сбросить все мои
   * изменения» (меню «Ещё» панели «Изменения»); `next` «Начать новую правку» после принятого
   * запроса. Новый вид без git-слов вне панели «Изменения».
   */
  variant?: "classic" | "reset" | "next";
  isOpen: boolean;
  onClose: () => void;
  onDone: () => void;
};

/**
 * «Начать заново от основной ветки» (4.3, шаг 5): дерево на свежую базу без
 * ветки, PR и отправленная вершина забываются, ветка на хостинге остаётся.
 * Несохранённые правки пропадают только по явной галочке.
 */
export const StartOverDialog = ({
  git,
  variant = "classic",
  isOpen,
  onClose,
  onDone,
}: StartOverDialogProps) => {
  const { t } = useTranslation("packStudio");
  const startOver = useStartPackOver(git.workspace.id);
  const [discard, setDiscard] = useState(false);
  const uid = useId();
  const base = git.base_branch ?? "";
  // Слова: у `classic` прежние ключи, у новых видов отдельные (без «свежей main без ветки»).
  const words =
    variant === "classic"
      ? {
          title: t("git.startOver.title"),
          lead: t("git.startOver.lead", { base }),
          remote: t("git.startOver.remote"),
          submit: t("git.startOver.submit"),
          done: t("git.startOver.done", { base }),
        }
      : {
          title: t(`git.startOver.${variant}.title`),
          lead: t(`git.startOver.${variant}.lead`),
          remote: t("git.startOver.remoteSpace"),
          submit: t(`git.startOver.${variant}.submit`),
          done: t(`git.startOver.${variant}.done`),
        };

  const close = () => {
    if (startOver.isPending) return;
    startOver.reset();
    setDiscard(false);
    onClose();
  };

  const submit = () => {
    startOver.mutate(git.dirty && discard, {
      onSuccess: () => {
        toast.success(words.done);
        onDone();
        startOver.reset();
        setDiscard(false);
        onClose();
      },
    });
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={close}
      title={words.title}
      description={words.lead}
      width={520}
      footer={
        <>
          <Button variant="secondary" onClick={close}>
            {t("common.cancel")}
          </Button>
          <Button
            variant="danger"
            disabled={startOver.isPending || (git.dirty && !discard)}
            onClick={submit}
            data-testid="git-start-over-submit"
          >
            {words.submit}
          </Button>
        </>
      }
    >
      <div className="flex flex-col" style={{ gap: "0.75rem" }}>
        <p className="ps-dialog-text">{words.remote}</p>
        {git.dirty && (
          <>
            <Notice
              tone="warn"
              role="status"
              text={t("git.startOver.dirty", { count: git.uncommitted.length })}
            />
            <label className="ps-choice" htmlFor={`${uid}-discard`}>
              <input
                id={`${uid}-discard`}
                type="checkbox"
                checked={discard}
                onChange={(e) => {
                  setDiscard(e.target.checked);
                }}
                style={{ accentColor: "var(--c-err)" }}
                data-testid="git-start-over-discard"
              />
              <span className="ps-choice-text">
                <span>
                  {t("git.startOver.discard", {
                    count: git.uncommitted.length,
                  })}
                </span>
              </span>
            </label>
          </>
        )}
        {startOver.isError && (
          <Notice
            tone="err"
            role="alert"
            text={<PackErrorText error={startOver.error} />}
          />
        )}
      </div>
    </Modal>
  );
};
