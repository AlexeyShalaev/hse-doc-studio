import { useState, type ReactNode } from "react";
import { useNavigate } from "react-router";
import { useIsMutating } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import {
  AUTHOR_PROFILE_PATH,
  describeGitError,
  gitConflictsPath,
  gitSyncMutationKeys,
  gitSettingsPath,
  useCancelOperation,
  useSyncUiStore,
  useUpdateGitSettings,
} from "@entities/git-sync";
import { toast } from "@shared/lib";
import { Spinner } from "@shared/ui/Spinner";
import { useNowTick } from "../model/useNowTick";
import { useSyncText } from "../model/useSyncText";
import { useSyncView } from "../model/useSyncView";
import { SyncPanelView, type SyncHistoryMode } from "./SyncPanelView";

export type SyncPanelProps = {
  projectId: string;
  /** Страница открывает окно подключения; панель само окно не знает. */
  onConnect: () => void;
  /** Нет обработчика: кнопки обмена файлом не показываются. */
  onBundle?: () => void;
  onShowInHistory: (mode: SyncHistoryMode) => void;
  /** Что показать под списком пришедших версий, когда одна выбрана. */
  renderIncomingDetails?: (commitId: string) => ReactNode;
};

/**
 * Синхронизация в большом виде на странице истории. Запуск и проверка идут через
 * общую очередь команд: их выполняет элемент в заголовке окна, он же сообщает
 * итог тостом, поэтому уведомления не дублируются.
 */
export const SyncPanel = ({
  projectId,
  onConnect,
  onBundle,
  onShowInHistory,
  renderIncomingDetails,
}: SyncPanelProps) => {
  const { t } = useTranslation("gitSync");
  const navigate = useNavigate();
  const { status, ui, isLoading } = useSyncView(projectId);
  const now = useNowTick();
  const text = useSyncText(ui, now);
  const cancelOperation = useCancelOperation();
  const updateSettings = useUpdateGitSettings();
  const isStarting =
    useIsMutating({ mutationKey: gitSyncMutationKeys.start }) > 0;
  const isChecking =
    useIsMutating({ mutationKey: gitSyncMutationKeys.fetch }) > 0;
  const [selected, setSelected] = useState<string | null>(null);

  if (isLoading) {
    return (
      <div className="flex justify-center" style={{ padding: 16 }}>
        <Spinner size="sm" />
      </div>
    );
  }
  if (!status || !ui.visible) return null;

  const selectedIncomingId = status.incoming.some((c) => c.id === selected)
    ? selected
    : null;

  return (
    <SyncPanelView
      ui={ui}
      status={status}
      text={text}
      now={now}
      isStarting={isStarting}
      isChecking={isChecking}
      isCancelling={cancelOperation.isPending}
      isAcknowledging={updateSettings.isPending}
      onSync={() => {
        useSyncUiStore.getState().requestCommand("run");
      }}
      onCheck={() => {
        useSyncUiStore.getState().requestCommand("check");
      }}
      onCancel={() => {
        const id = status.operation?.id;
        if (!id) return;
        cancelOperation.mutate(id, {
          onError: (error) => {
            toast.error(describeGitError(error, t("toast.failedUnknown")));
          },
        });
      }}
      onConnect={onConnect}
      {...(onBundle ? { onBundle } : {})}
      onFixAccess={() => {
        useSyncUiStore.getState().openConnectDialog("fix_access");
      }}
      onResolve={() => {
        void navigate(gitConflictsPath(projectId));
      }}
      onOpenSettings={() => {
        void navigate(gitSettingsPath(projectId));
      }}
      onOpenProfile={() => {
        void navigate(AUTHOR_PROFILE_PATH);
      }}
      onAcknowledgeSharedFolder={() => {
        updateSettings.mutate(
          { projectId, params: { shared_folder_ack: true } },
          {
            onError: (error) => {
              toast.error(describeGitError(error, t("toast.failedUnknown")));
            },
          },
        );
      }}
      onShowInHistory={onShowInHistory}
      selectedIncomingId={selectedIncomingId}
      onSelectIncoming={setSelected}
      {...(selectedIncomingId !== null && renderIncomingDetails
        ? { incomingDetails: renderIncomingDetails(selectedIncomingId) }
        : {})}
    />
  );
};
