import { useTranslation } from "react-i18next";
import { CloudProjectOpener, type CloudEntry } from "@entities/git-server";
import { Modal } from "@shared/ui/Modal";

export type CloudOpenDialogProps = {
  /** Что открываем; null закрывает окно. */
  entry: CloudEntry | null;
  onClose: () => void;
  onOpened: (projectId: string) => void;
  onReconnect: (serverUrl: string) => void;
};

/** Окно открытия облачного проекта: прогресс скачивания и переход в проект. */
export const CloudOpenDialog = ({
  entry,
  onClose,
  onOpened,
  onReconnect,
}: CloudOpenDialogProps) => {
  const { t } = useTranslation("localStudio");
  return (
    <Modal
      isOpen={entry !== null}
      onClose={onClose}
      width={460}
      title={t("cloud.dialog.title", { name: entry?.project.name ?? "" })}
    >
      {entry && (
        <CloudProjectOpener
          key={entry.project.id}
          credentialId={entry.server.credential_id}
          projectId={entry.project.id}
          onOpened={onOpened}
          onExit={onClose}
          onReconnect={() => {
            onReconnect(entry.server.server_url);
          }}
        />
      )}
    </Modal>
  );
};
