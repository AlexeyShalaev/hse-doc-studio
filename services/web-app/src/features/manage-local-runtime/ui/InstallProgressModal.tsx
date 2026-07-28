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
          style={{ width: 720, maxWidth: "calc(100vw - 32px)" }}
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
              padding: "12px 18px",
              borderBottom: "1px solid var(--border)",
              gap: 12,
            }}
          >
            <div className="flex items-center" style={{ gap: 8 }}>
              <Download size={14} style={{ color: "var(--accent)" }} />
              <h3 style={{ fontSize: 14, fontWeight: 600, margin: 0 }}>
                {title}
              </h3>
              <span
                className="mono dim"
                style={{ fontSize: 11.5 }}
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
              <X size={14} />
            </button>
          </div>

          <div
            ref={logRef}
            className="mono"
            style={{
              padding: 12,
              height: 360,
              overflowY: "auto",
              background: "var(--bg-0)",
              borderBottom: "1px solid var(--border)",
              fontSize: 11.5,
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
            style={{ padding: "10px 18px", gap: 12 }}
          >
            <div className="flex items-center" style={{ gap: 8, fontSize: 12 }}>
              {state === "running" && (
                <>
                  <Spinner size="sm" />
                  <span>{t("installModal.loading")}</span>
                </>
              )}
              {state === "success" && (
                <>
                  <CheckCircle2 size={14} style={{ color: "var(--c-ok)" }} />
                  <span style={{ color: "var(--c-ok)" }}>
                    {t("installModal.done")}
                  </span>
                </>
              )}
              {state === "failure" && (
                <>
                  <XCircle size={14} style={{ color: "var(--c-err)" }} />
                  <span style={{ color: "var(--c-err)" }}>
                    {t("installModal.failed")}
                  </span>
                </>
              )}
            </div>
            <div className="flex items-center" style={{ gap: 8 }}>
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
