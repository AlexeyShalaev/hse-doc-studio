import { useCallback, useMemo, useState, type ReactNode } from "react";
import * as DialogPrimitive from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { pickLocalized } from "@shared/lib";
import { Modal } from "@shared/ui";
import {
  previewMemoryKey,
  readPreviewMemory,
  writePreviewMemory,
} from "../../lib/previewStore";
import { useSheetHistory } from "../../lib/useSheetHistory";
import { useOutcomeModel } from "../../model";
import { PreviewUiContext, type PreviewUi } from "./context";
import { PreviewPanel } from "./PreviewPanel";

type PreviewHostProps = {
  children: ReactNode;
  /** Документ, чей предпросмотр открыт сразу (галерея состояний); сборка сама не стартует. */
  initialDocument?: string | null;
};

/**
 * Предпросмотр PDF рядом с результатом (срез F12): на компьютере выдвижная панель справа, не
 * закрывающая экран (вводные и сценарий остаются доступными, автосборка идёт за ними), на
 * телефоне нижний лист. Открытый документ переживает уход в «Файлы» и возврат: правка файла
 * там делает сборку устаревшей, и автосборка собирает её заново.
 */
export const PreviewHost = ({
  children,
  initialDocument = null,
}: PreviewHostProps) => {
  const { t, i18n } = useTranslation("packOutcome");
  const model = useOutcomeModel();
  const { workspaceId, ref, phone, url, shown, view } = model;
  const key = previewMemoryKey(workspaceId, ref);
  const [document, setDocument] = useState<string | null>(
    () => initialDocument ?? (phone ? null : readPreviewMemory(key).document),
  );
  // Явное открытие собирает документ сразу; возврат из «Файлов» и галерея нет.
  const [explicit, setExplicit] = useState(false);

  // Предпросмотр собирает рабочее дерево и нужен автору, а не студенту.
  const student = view === "student";
  const fromWorkTree = url.state.state === "work_tree";
  const available = !student && fromWorkTree;

  const open = useCallback(
    (next: string) => {
      setExplicit(true);
      setDocument(next);
      if (readPreviewMemory(key).document !== next) {
        writePreviewMemory(key, { document: next, built: null });
      }
    },
    [key],
  );
  const close = useCallback(() => {
    setDocument(null);
    setExplicit(false);
    writePreviewMemory(key, { document: null });
  }, [key]);

  const ui = useMemo<PreviewUi>(
    () => ({
      open,
      close,
      document,
      available,
      unavailableReason: student ? "student" : fromWorkTree ? null : "state",
    }),
    [open, close, document, available, student, fromWorkTree],
  );

  const shownDocument = available ? document : null;
  useSheetHistory("preview", phone && shownDocument !== null, close);
  const doc = shown?.documents.find((d) => d.id === shownDocument);
  const name = doc
    ? pickLocalized(doc.name, i18n.language, doc.id)
    : (shownDocument ?? "");
  const title = t("preview.titleFor", { name });
  const panel = shownDocument !== null && (
    <PreviewPanel
      key={shownDocument}
      document={shownDocument}
      buildOnMount={explicit}
      memoryKey={key}
    />
  );

  return (
    <PreviewUiContext.Provider value={ui}>
      {children}
      {phone ? (
        <Modal
          isOpen={shownDocument !== null}
          onClose={close}
          title={title}
          width={560}
          className="po-sheet"
        >
          {panel}
        </Modal>
      ) : (
        <DialogPrimitive.Root
          open={shownDocument !== null}
          modal={false}
          onOpenChange={(next) => {
            if (!next) close();
          }}
        >
          <DialogPrimitive.Portal>
            <DialogPrimitive.Content
              className="po-preview ui-console"
              data-testid="outcome-preview-drawer"
              aria-describedby={undefined}
              // Панель не модальная: вводные и сценарий рядом остаются доступными.
              onInteractOutside={(event) => {
                event.preventDefault();
              }}
            >
              <header className="po-preview-head">
                <DialogPrimitive.Title className="po-preview-title">
                  {title}
                </DialogPrimitive.Title>
                <DialogPrimitive.Close
                  className="icon-btn sm"
                  aria-label={t("preview.close")}
                  title={t("preview.close")}
                  data-testid="outcome-preview-close"
                >
                  <X size="0.875rem" aria-hidden="true" />
                </DialogPrimitive.Close>
              </header>
              <div className="po-preview-scroll">{panel}</div>
            </DialogPrimitive.Content>
          </DialogPrimitive.Portal>
        </DialogPrimitive.Root>
      )}
    </PreviewUiContext.Provider>
  );
};
