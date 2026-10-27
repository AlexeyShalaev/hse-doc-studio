import { useEffect } from "react";
import { useSyncUiStore, type ConnectDialogMode } from "@entities/git-sync";
import { GALLERY_PROJECT_ID } from "@shared/lib/stateGallery";
import { ConnectRemoteDialog } from "../ui/ConnectRemoteDialog";

export const ConnectLauncher = ({
  mode,
  url,
}: {
  mode: ConnectDialogMode;
  /** Адрес, который окно подставит в поле. */
  url?: string;
}) => {
  // Запись открыта нажатием «Открыть»: окно появляется сразу.
  useEffect(() => {
    useSyncUiStore.getState().openConnectDialog(mode);
    return () => {
      useSyncUiStore.getState().closeConnectDialog();
    };
  }, [mode]);
  return (
    <div className="flex items-center flex-wrap" style={{ gap: 12 }}>
      <button
        type="button"
        className="btn"
        onClick={() => {
          useSyncUiStore.getState().openConnectDialog(mode);
        }}
      >
        Открыть окно
      </button>
      <ConnectRemoteDialog
        projectId={GALLERY_PROJECT_ID}
        {...(url === undefined ? {} : { initialUrl: url })}
      />
    </div>
  );
};
