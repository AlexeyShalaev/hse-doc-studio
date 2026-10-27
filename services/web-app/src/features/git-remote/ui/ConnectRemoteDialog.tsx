import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useSyncUiStore, type ConnectDialogMode } from "@entities/git-sync";
import { Modal } from "@shared/ui/Modal";
import { ConnectFlow, type CloneTarget } from "./ConnectFlow";

export type ConnectRemoteDialogProps = {
  projectId: string;
  /**
   * «Клонировать в новую папку», когда в репозитории лежит другой проект. Окно
   * клонирования устроено в другой фиче, поэтому переход передаёт страница или
   * виджет; без него кнопки в карточке нет.
   */
  onCloneInstead?: (target: CloneTarget) => void;
  /** Адрес, который окно подставит в первое поле (галерея состояний). */
  initialUrl?: string;
};

/**
 * Окно «Подключить репозиторий». Открывается из заголовка, палитры, настроек и
 * панели синхронизации через общее состояние (`useSyncUiStore.connectDialog`),
 * поэтому достаточно одного экземпляра на проект. Режим `fix_access` начинается
 * с шага доступа и обновляет доступ уже подключённого репозитория.
 */
export const ConnectRemoteDialog = ({
  projectId,
  onCloneInstead,
  initialUrl,
}: ConnectRemoteDialogProps) => {
  const { t } = useTranslation("gitRemote");
  const dialog = useSyncUiStore((state) => state.connectDialog);
  const close = useSyncUiStore((state) => state.closeConnectDialog);
  // Пока окно закрывается, держим прежний режим: заголовок не должен мигать.
  const [lastMode, setLastMode] = useState<ConnectDialogMode>("connect");
  if (dialog && dialog.mode !== lastMode) setLastMode(dialog.mode);
  const mode = dialog?.mode ?? lastMode;

  return (
    <Modal
      isOpen={dialog !== null}
      onClose={close}
      width={680}
      title={mode === "fix_access" ? t("connect.titleFix") : t("connect.title")}
      description={
        mode === "fix_access"
          ? t("connect.descriptionFix")
          : t("connect.description")
      }
    >
      <ConnectFlow
        projectId={projectId}
        mode={mode}
        onClose={close}
        onCloneInstead={onCloneInstead}
        initialUrl={initialUrl}
      />
    </Modal>
  );
};
