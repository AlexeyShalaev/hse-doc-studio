import { useTranslation } from "react-i18next";
import { Notice } from "@shared/ui/ConflictKit";

export type SharedFolderWarningProps = {
  /** Ключ из gitAccess:sharedProvider: yandex_disk, dropbox и так далее. */
  provider: string;
  /** «Понятно»: запоминает, что предупреждение прочитано для этого проекта. */
  onAcknowledge?: () => void;
  isBusy?: boolean;
};

// Папка проекта лежит в облачном диске: если диск синхронизирует и файлы, и
// историю, она может повредиться. Только предупреждение, подключению не мешает.
export const SharedFolderWarning = ({
  provider,
  onAcknowledge,
  isBusy = false,
}: SharedFolderWarningProps) => {
  const { t } = useTranslation("gitRemote");
  const { t: tAccess } = useTranslation("gitAccess");
  const name = tAccess(`sharedProvider.${provider}`, {
    defaultValue: tAccess("sharedProvider.unknown"),
  });
  return (
    <div data-testid="shared-folder-warning">
      <Notice
        tone="warn"
        role="status"
        text={
          <>
            <strong style={{ display: "block", fontWeight: 600 }}>
              {t("sharedFolder.title", { provider: name })}
            </strong>
            {t("sharedFolder.text")}
          </>
        }
        action={
          onAcknowledge && (
            <button
              type="button"
              className="btn xs"
              disabled={isBusy}
              onClick={onAcknowledge}
            >
              {t("sharedFolder.acknowledge")}
            </button>
          )
        }
      />
    </div>
  );
};
