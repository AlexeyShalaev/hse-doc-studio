import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { packErrorText, usePackDiff } from "@entities/pack-studio";
import { DiffPatch, EmptyState, ErrorState, Modal, Spinner } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import { splitDiff } from "../lib/splitDiff";

export type DiffDialogProps = {
  workspaceId: string;
  baseBranch: string | null;
  isOpen: boolean;
  onClose: () => void;
};

/** Изменения от основной ветки: коммиты ветки и правки на диске, по файлам. */
export const DiffDialog = ({
  workspaceId,
  baseBranch,
  isOpen,
  onClose,
}: DiffDialogProps) => {
  const { t } = useTranslation("packStudio");
  const diff = usePackDiff(workspaceId, isOpen);
  const files = useMemo(
    () => (diff.data ? splitDiff(diff.data.diff) : []),
    [diff.data],
  );

  let body: React.ReactNode;
  if (diff.isPending) {
    body = (
      <div className="flex justify-center" style={{ padding: "2rem" }}>
        <Spinner size="md" />
      </div>
    );
  } else if (diff.isError) {
    body = (
      <ErrorState
        compact
        description={packErrorText(diff.error)}
        onRetry={() => void diff.refetch()}
      />
    );
  } else if (files.length === 0) {
    body = (
      <EmptyState
        compact
        title={t("git.diff.emptyTitle")}
        description={t("git.diff.emptyLead", { base: baseBranch ?? "" })}
        testId="git-diff-empty"
      />
    );
  } else {
    body = (
      <div className="flex flex-col" style={{ gap: "0.75rem" }}>
        {diff.data.truncated && (
          <Notice tone="warn" role="status" text={t("git.diff.truncated")} />
        )}
        {files.map((file) => (
          <DiffPatch
            key={file.path}
            file={file}
            stat={file.stat}
            maxHeight={360}
          />
        ))}
      </div>
    );
  }

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={t("git.diff.title")}
      description={t("git.diff.lead", { base: baseBranch ?? "" })}
      width={880}
    >
      <div data-testid="git-diff">{body}</div>
    </Modal>
  );
};
