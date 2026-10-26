import { useEffect } from "react";
import { useNavigate } from "react-router";
import { useTranslation } from "react-i18next";
import {
  gitHistoryPath,
  gitSettingsPath,
  useSyncUiStore,
} from "@entities/git-sync";
import { Popover, PopoverContent } from "@shared/ui/Popover";
import { useBackgroundFetch } from "../model/useBackgroundFetch";
import { useIncomingToast } from "../model/useIncomingToast";
import { useNowTick } from "../model/useNowTick";
import { useSyncAnnouncer } from "../model/useSyncAnnouncer";
import { useSyncController } from "../model/useSyncController";
import { useSyncText } from "../model/useSyncText";
import { SyncButton, SyncButtonSkeleton } from "./SyncButton";
import { SyncLiveRegion } from "./SyncLiveRegion";
import { SyncPopover } from "./SyncPopover";

export type SyncControlProps = {
  projectId: string;
};

/**
 * Вход в синхронизацию в заголовке окна проекта: кнопка с состоянием, панель
 * подробностей, фоновая проверка при открытии и возврате в окно, уведомления и
 * озвучивание переходов. Один экземпляр на проект: команды палитры и сочетание
 * клавиш приходят сюда через общее хранилище.
 */
export const SyncControl = ({ projectId }: SyncControlProps) => {
  const { t } = useTranslation("gitSync");
  const navigate = useNavigate();
  const controller = useSyncController(projectId);
  const { status, ui, isLoading } = controller;
  const now = useNowTick();
  const text = useSyncText(ui, now);
  const isOpen = useSyncUiStore((state) => state.popoverOpen);
  const setOpen = useSyncUiStore((state) => state.setPopoverOpen);
  const announcement = useSyncAnnouncer(ui);

  useBackgroundFetch(projectId, controller);
  useIncomingToast(projectId, controller, () => {
    void controller.run();
  });

  // Панель не должна «переехать» в следующий проект открытой.
  useEffect(
    () => () => {
      useSyncUiStore.getState().setPopoverOpen(false);
    },
    [projectId],
  );

  if (isLoading) return <SyncButtonSkeleton />;
  if (!status || !ui.visible) return null;

  const closeThen = (go: () => void) => () => {
    setOpen(false);
    go();
  };

  return (
    <>
      <Popover open={isOpen} onOpenChange={setOpen}>
        <SyncButton
          ui={ui}
          text={text}
          isOpen={isOpen}
          onPrimary={() => {
            controller.runPrimary(ui.primary);
          }}
          onToggleDetails={() => {
            setOpen(!isOpen);
          }}
        />
        <PopoverContent
          width={400}
          aria-label={t("popover.title")}
          onOpenAutoFocus={(event) => {
            // Фокус на саму панель, а не на первую ссылку внутри: так нет
            // случайной рамки, а Tab ведёт по действиям по порядку.
            event.preventDefault();
            if (event.currentTarget instanceof HTMLElement) {
              event.currentTarget.focus();
            }
          }}
          onInteractOutside={(event) => {
            // Щелчок по самой кнопке и по сегменту в строке состояния сам решает,
            // открыть панель или закрыть: иначе она закрылась бы и тут же открылась.
            const target = event.target;
            if (
              target instanceof Element &&
              target.closest("[data-sync-trigger]")
            ) {
              event.preventDefault();
            }
          }}
        >
          <SyncPopover
            ui={ui}
            status={status}
            text={text}
            now={now}
            isStarting={controller.isStarting}
            isChecking={controller.isChecking}
            isCancelling={controller.isCancelling}
            onSync={() => {
              void controller.run();
            }}
            onCheck={() => {
              void controller.check();
            }}
            onCancel={controller.cancel}
            onConnect={() => {
              useSyncUiStore.getState().openConnectDialog("connect");
            }}
            onFixAccess={() => {
              useSyncUiStore.getState().openConnectDialog("fix_access");
            }}
            onResolve={closeThen(controller.openConflicts)}
            onOpenSettings={closeThen(() => {
              void navigate(gitSettingsPath(projectId));
            })}
            onOpenHistory={closeThen(() => {
              void navigate(gitHistoryPath(projectId));
            })}
            onOpenProfile={() => {
              useSyncUiStore.getState().openProfileDialog();
            }}
          />
        </PopoverContent>
      </Popover>
      <SyncLiveRegion announcement={announcement} />
    </>
  );
};
