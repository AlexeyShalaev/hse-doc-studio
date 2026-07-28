import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import * as DialogPrimitive from "@radix-ui/react-dialog";
import { CheckCircle2, Download, X, XCircle } from "lucide-react";
import { Spinner } from "@shared/ui/Spinner";
import {
  useInvalidateOfficeServices,
  type OfficeServiceId,
} from "@entities/office-services";
import { useOfficeInstallStream } from "../lib/useOfficeInstallStream";

export type InstallOfficeImageTarget = {
  service: OfficeServiceId;
  image: string;
};

export type InstallOfficeImageModalProps = {
  target: InstallOfficeImageTarget | null;
  onClose: () => void;
};

export const InstallOfficeImageModal = ({
  target,
  onClose,
}: InstallOfficeImageModalProps) => {
  const { t } = useTranslation("installOfficeImage");
  const { state, lines, start, reset } = useOfficeInstallStream();
  const invalidate = useInvalidateOfficeServices();
  const logRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (target) {
      start(target.service, target.image);
    } else {
      reset();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target]);

  useEffect(() => {
    const el = logRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [lines.length]);

  useEffect(() => {
    if (state === "success") {
      invalidate();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state]);

  const isOpen = target !== null;

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
            {t("modal.title")}
          </DialogPrimitive.Title>
          <DialogPrimitive.Description className="sr-only">
            {t("modal.description")}
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
                {t("modal.title")}
              </h3>
              <span
                className="mono dim"
                style={{ fontSize: 11.5 }}
                title={target?.image ?? ""}
              >
                {target?.image}
              </span>
            </div>
            <button
              type="button"
              className="icon-btn"
              onClick={onClose}
              title={t("modal.close")}
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
              <div className="dim">[…]</div>
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
                  <span>{t("status.running")}</span>
                </>
              )}
              {state === "success" && (
                <>
                  <CheckCircle2 size={14} style={{ color: "var(--c-ok)" }} />
                  <span style={{ color: "var(--c-ok)" }}>
                    {t("status.success")}
                  </span>
                </>
              )}
              {state === "failure" && (
                <>
                  <XCircle size={14} style={{ color: "var(--c-err)" }} />
                  <span style={{ color: "var(--c-err)" }}>
                    {t("status.failure")}
                  </span>
                </>
              )}
            </div>
            <div className="flex items-center" style={{ gap: 8 }}>
              {state === "failure" && target !== null && (
                <button
                  type="button"
                  className="btn xs"
                  onClick={() => {
                    start(target.service, target.image);
                  }}
                >
                  {t("actions.retry")}
                </button>
              )}
              <button type="button" className="btn xs" onClick={onClose}>
                {state === "success" ? t("actions.done") : t("actions.close")}
              </button>
            </div>
          </div>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
};
