import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import * as DialogPrimitive from "@radix-ui/react-dialog";
import { CheckCircle2, Download, X, XCircle } from "lucide-react";
import { Spinner } from "@shared/ui/Spinner";
import { useSseInstall } from "../lib/useSseInstall";

export type InstallProgressModalProps = {
  title: string;
  // The thing being installed (engine image / model tag), shown in the header.
  target: string | null;
  // Full SSE URL to stream; null closes the modal.
  url: string | null;
  onClose: () => void;
  onSuccess?: () => void;
};

export const InstallProgressModal = ({
  title,
  target,
  url,
  onClose,
  onSuccess,
}: InstallProgressModalProps) => {
  const { t } = useTranslation("localRuntime");
  const { state, lines, start, reset } = useSseInstall();
  const logRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (url) {
      start(url);
    } else {
      reset();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [url]);

  useEffect(() => {
    const el = logRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [lines.length]);

  useEffect(() => {
    if (state === "success") {
      onSuccess?.();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state]);

  const isOpen = url !== null;

  return (
    <DialogPrimitive.Root
      open={isOpen}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="scrim" />
        <DialogPrimitive.Content
          className="modal-panel fixed left-1/2 top-1/2 z-[102] -translate-x-1/2 -translate-y-1/2"
          style={{ width: "45rem", maxWidth: "calc(100vw - 2rem)" }}
        >
          <DialogPrimitive.Title className="sr-only">
            {title}
          </DialogPrimitive.Title>
          <DialogPrimitive.Description className="sr-only">
            {t("installModal.description")}
          </DialogPrimitive.Description>

          <div
            className="flex items-center justify-between"
            style={{
              padding: "0.75rem 1.125rem",
              borderBottom: "1px solid var(--border)",
              gap: "0.75rem",
            }}
          >
            <div className="flex items-center" style={{ gap: "0.5rem" }}>
              <Download size="0.875rem" style={{ color: "var(--accent)" }} />
              <h3 style={{ fontSize: "0.875rem", fontWeight: 600, margin: 0 }}>
                {title}
              </h3>
              <span
                className="mono dim"
                style={{ fontSize: "0.71875rem" }}
                title={target ?? ""}
              >
                {target}
              </span>
            </div>
            <button
              type="button"
              className="icon-btn"
              onClick={onClose}
              title={t("installModal.close")}
            >
              <X size="0.875rem" />
            </button>
          </div>

          <div
            ref={logRef}
            className="mono"
            style={{
              padding: "0.75rem",
              height: "22.5rem",
              overflowY: "auto",
              background: "var(--bg-0)",
              borderBottom: "1px solid var(--border)",
              fontSize: "0.71875rem",
              lineHeight: 1.45,
              whiteSpace: "pre",
            }}
          >
            {lines.length === 0 ? (
              <div className="dim">{t("installModal.logEmpty")}</div>
            ) : (
              lines.map((line, i) => (
                <div key={i} style={{ wordBreak: "break-all" }}>
                  {line}
                </div>
              ))
            )}
          </div>

          <div
            className="flex items-center justify-between"
            style={{ padding: "0.625rem 1.125rem", gap: "0.75rem" }}
          >
            <div
              className="flex items-center"
              style={{ gap: "0.5rem", fontSize: "0.75rem" }}
            >
              {state === "running" && (
                <>
                  <Spinner size="sm" />
                  <span>{t("installModal.loading")}</span>
                </>
              )}
              {state === "success" && (
                <>
                  <CheckCircle2
                    size="0.875rem"
                    style={{ color: "var(--c-ok)" }}
                  />
                  <span style={{ color: "var(--c-ok)" }}>
                    {t("installModal.done")}
                  </span>
                </>
              )}
              {state === "failure" && (
                <>
                  <XCircle size="0.875rem" style={{ color: "var(--c-err)" }} />
                  <span style={{ color: "var(--c-err)" }}>
                    {t("installModal.failed")}
                  </span>
                </>
              )}
            </div>
            <div className="flex items-center" style={{ gap: "0.5rem" }}>
              {state === "failure" && url !== null && (
                <button
                  type="button"
                  className="btn xs"
                  onClick={() => {
                    start(url);
                  }}
                >
                  {t("installModal.retry")}
                </button>
              )}
              <button type="button" className="btn xs" onClick={onClose}>
                {state === "success"
                  ? t("installModal.closeDone")
                  : t("installModal.closeButton")}
              </button>
            </div>
          </div>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
};
