import type { ReactNode } from "react";
import { FileText, Maximize2, PenLine, ScrollText, Square } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  packErrorText,
  packPreviewPdfUrl,
  useCancelPackPreview,
  usePackPreviewLog,
  type PackPreviewBuild,
} from "@entities/pack-studio";
import { Button, ErrorState, Modal, PdfViewer, Spinner } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import { useBuildErrorText } from "../lib/buildErrorText";

export type BuildViewMode = "pdf" | "places";

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

/** Сборка: очередь, идёт, готова (PDF), не удалась, отменена. */
export const BuildView = ({
  workspaceId,
  build,
  stale,
  onLog,
  onFull,
  places,
  mode,
  onMode,
}: {
  workspaceId: string;
  build: PackPreviewBuild;
  stale: boolean;
  onLog: () => void;
  onFull: () => void;
  places: ReactNode;
  mode: BuildViewMode;
  onMode: (mode: BuildViewMode) => void;
}) => {
  const { t } = useTranslation("packStudio");
  const cancel = useCancelPackPreview(workspaceId);
  const errorText = useBuildErrorText();

  if (build.status === "queued" || build.status === "running") {
    return (
      <div className="ps-preview-state" data-testid="preview-running">
        <Spinner size="sm" />
        <span>{t(`preview.status.${build.status}`)}</span>
        <Button
          size="xs"
          variant="ghost"
          disabled={cancel.isPending}
          onClick={() => {
            cancel.mutate(build.id);
          }}
          data-testid="preview-cancel"
        >
          <Square size="0.6875rem" />
          {t("preview.cancel")}
        </Button>
        {cancel.isError && (
          <Notice tone="err" role="alert" text={packErrorText(cancel.error)} />
        )}
      </div>
    );
  }
  if (build.status === "cancelled") {
    return (
      <p className="ps-pane-empty" data-testid="preview-cancelled">
        {t("preview.status.cancelled")}
      </p>
    );
  }
  if (build.status === "failed") {
    return (
      <div className="flex flex-col" style={{ gap: "0.5rem" }}>
        <Notice
          tone="err"
          role="alert"
          text={
            <span data-testid="preview-failed">
              {errorText(build.error?.code ?? "unknown")}
              {build.error?.detail && (
                <span className="ps-preview-detail mono">
                  {build.error.detail}
                </span>
              )}
            </span>
          }
          action={
            <Button
              size="xs"
              variant="secondary"
              onClick={onLog}
              data-testid="preview-failed-log"
            >
              <ScrollText size="0.6875rem" />
              {t("preview.log")}
            </Button>
          }
        />
      </div>
    );
  }
  const showPlaces = mode === "places" && places !== null;
  return (
    <div className="ps-preview-pdf" data-testid="preview-pdf">
      {places !== null && (
        <div
          className="ps-view-tabs ps-preview-modes"
          role="tablist"
          aria-label={t("places.modes")}
        >
          <button
            type="button"
            role="tab"
            aria-selected={!showPlaces}
            className={showPlaces ? "ps-view-tab" : "ps-view-tab active"}
            onClick={() => {
              onMode("pdf");
            }}
            data-testid="preview-mode-pdf"
          >
            <FileText size="0.75rem" aria-hidden="true" />
            {t("places.modePdf")}
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={showPlaces}
            className={showPlaces ? "ps-view-tab active" : "ps-view-tab"}
            onClick={() => {
              onMode("places");
            }}
            data-testid="preview-mode-places"
          >
            <PenLine size="0.75rem" aria-hidden="true" />
            {t("places.title")}
          </button>
        </div>
      )}
      <div className="ps-preview-meta">
        <span>
          {[
            build.pages !== null
              ? t("preview.pages", { count: build.pages })
              : null,
            build.cached ? t("preview.cached") : null,
          ]
            .filter(Boolean)
            .join(" · ")}
        </span>
        <span className="ps-editor-actions">
          <Button
            size="xs"
            variant="ghost"
            onClick={onLog}
            data-testid="preview-log-open"
          >
            <ScrollText size="0.6875rem" />
            {t("preview.log")}
          </Button>
          <Button
            size="xs"
            variant="ghost"
            onClick={onFull}
            title={t("preview.full")}
            aria-label={t("preview.full")}
            data-testid="preview-full"
          >
            <Maximize2 size="0.6875rem" />
          </Button>
        </span>
      </div>
      {stale && <Notice tone="info" role="status" text={t("preview.stale")} />}
      {showPlaces ? (
        places
      ) : (
        <div className="ps-preview-viewer">
          <PdfViewer
            url={packPreviewPdfUrl(workspaceId, build.id)}
            refreshKey={build.id}
            ariaLabel={build.document}
            initialFit
          />
        </div>
      )}
    </div>
  );
};

/** Готовый PDF сборки во весь экран. */
export const PdfFullModal = ({
  workspaceId,
  build,
  isOpen,
  onClose,
}: {
  workspaceId: string;
  build: PackPreviewBuild | undefined;
  isOpen: boolean;
  onClose: () => void;
}) => {
  const { t } = useTranslation("packStudio");
  return (
    <Modal
      isOpen={isOpen && build?.status === "succeeded"}
      onClose={onClose}
      title={t("preview.title")}
      width={980}
    >
      {build?.status === "succeeded" && (
        <div style={{ height: "75vh", minHeight: "20rem" }}>
          <PdfViewer
            url={packPreviewPdfUrl(workspaceId, build.id)}
            refreshKey={build.id}
            ariaLabel={build.document}
          />
        </div>
      )}
    </Modal>
  );
};
