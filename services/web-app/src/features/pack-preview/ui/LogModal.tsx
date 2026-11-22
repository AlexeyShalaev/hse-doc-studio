import { useTranslation } from "react-i18next";
import { packErrorText, usePackPreviewLog } from "@entities/pack-studio";
import { ErrorState, Modal, Spinner } from "@shared/ui";

/** Журнал сборки предпросмотра: текст журнала раннера в окне. */
export const LogModal = ({
  workspaceId,
  buildId,
  onClose,
}: {
  workspaceId: string;
  buildId: string | null;
  onClose: () => void;
}) => {
  const { t } = useTranslation("packStudio");
  const log = usePackPreviewLog(workspaceId, buildId);
  return (
    <Modal
      isOpen={buildId !== null}
      onClose={onClose}
      title={t("preview.log")}
      width={820}
    >
      {log.isPending ? (
        <div className="flex justify-center" style={{ padding: "2rem" }}>
          <Spinner size="md" />
        </div>
      ) : log.isError ? (
        <ErrorState
          compact
          description={packErrorText(log.error)}
          onRetry={() => void log.refetch()}
        />
      ) : (
        <pre className="ps-log mono" data-testid="preview-log">
          {log.data || t("preview.logEmpty")}
        </pre>
      )}
    </Modal>
  );
};
