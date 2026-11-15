import { useTranslation } from "react-i18next";
import { Button, Modal } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import { ChangedFiles } from "./ChangedFiles";

export type MergeConflictDialogProps = {
  /** Файлы конфликта от папки паков; null: окно закрыто. */
  files: string[] | null;
  baseBranch: string | null;
  onClose: () => void;
  onOpen: (path: string) => void;
};

/**
 * «Подтянуть основную ветку» упёрлось в конфликт: слияние отменено, ветка не
 * изменилась. Файлы конфликта правят в ветке и пробуют снова.
 */
export const MergeConflictDialog = ({
  files,
  baseBranch,
  onClose,
  onOpen,
}: MergeConflictDialogProps) => {
  const { t } = useTranslation("packStudio");
  return (
    <Modal
      isOpen={files !== null}
      onClose={onClose}
      title={t("git.merge.conflictTitle")}
      width={560}
      footer={<Button onClick={onClose}>{t("git.merge.ok")}</Button>}
    >
      <div
        className="flex flex-col"
        style={{ gap: "0.75rem" }}
        data-testid="git-merge-conflict"
      >
        <Notice
          tone="warn"
          role="alert"
          text={t("git.merge.conflictLead", { base: baseBranch ?? "" })}
        />
        {files && files.length > 0 && (
          <ChangedFiles
            files={files.map((path) => ({ path, status: "modified" as const }))}
            onOpen={(path) => {
              onClose();
              onOpen(path);
            }}
          />
        )}
        <p className="ps-dialog-text">{t("git.merge.conflictHint")}</p>
      </div>
    </Modal>
  );
};
