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
  isOpen,
  onClose,
  onDone,
}: StartOverDialogProps) => {
  const { t } = useTranslation("packStudio");
  const startOver = useStartPackOver(git.workspace.id);
  const [discard, setDiscard] = useState(false);
  const uid = useId();

  const close = () => {
    if (startOver.isPending) return;
    startOver.reset();
    setDiscard(false);
    onClose();
  };

  const submit = () => {
    startOver.mutate(git.dirty && discard, {
      onSuccess: () => {
        toast.success(t("git.startOver.done", { base: git.base_branch ?? "" }));
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
      title={t("git.startOver.title")}
      description={t("git.startOver.lead", { base: git.base_branch ?? "" })}
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
            {t("git.startOver.submit")}
          </Button>
        </>
      }
    >
      <div className="flex flex-col" style={{ gap: "0.75rem" }}>
        <p className="ps-dialog-text">{t("git.startOver.remote")}</p>
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
