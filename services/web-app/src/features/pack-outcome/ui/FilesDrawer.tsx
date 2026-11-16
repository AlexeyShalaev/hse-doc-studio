import * as DialogPrimitive from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { PackTreePanel } from "@features/pack-tree";

type FilesDrawerProps = {
  workspaceId: string;
  open: boolean;
  onClose: () => void;
  /** Файл выбран: экран открывает режим «Файлы» на нём. */
  onSelect: (path: string) => void;
};

/**
 * Выдвижная панель «Файлы» с прежним деревом пака (template-studio-outcome.md, 3.9). Это не
 * замена режима «Файлы», а быстрый переход к нужному файлу из экрана результата.
 */
export const FilesDrawer = ({
  workspaceId,
  open,
  onClose,
  onSelect,
}: FilesDrawerProps) => {
  const { t } = useTranslation("packOutcome");
  return (
    <DialogPrimitive.Root
      open={open}
      onOpenChange={(next) => {
        if (!next) onClose();
      }}
    >
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="scrim po-drawer-scrim" />
        <DialogPrimitive.Content
          className="po-drawer ui-console"
          data-testid="outcome-files-drawer"
        >
          <header className="po-drawer-head">
            <DialogPrimitive.Title className="po-drawer-title">
              {t("drawer.title")}
            </DialogPrimitive.Title>
            <DialogPrimitive.Close
              className="icon-btn sm"
              aria-label={t("drawer.close")}
              title={t("drawer.close")}
              data-testid="outcome-files-close"
            >
              <X size="0.875rem" aria-hidden="true" />
            </DialogPrimitive.Close>
          </header>
          <DialogPrimitive.Description className="po-drawer-lead">
            {t("drawer.lead")}
          </DialogPrimitive.Description>
          <div className="po-drawer-body">
            <PackTreePanel
              workspaceId={workspaceId}
              selectedPath={null}
              onSelect={onSelect}
            />
          </div>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
};
