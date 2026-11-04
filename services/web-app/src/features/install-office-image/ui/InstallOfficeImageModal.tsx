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
          style={{ width: "45rem", maxWidth: "calc(100vw - 2rem)" }}
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
              padding: "0.75rem 1.125rem",
              borderBottom: "1px solid var(--border)",
              gap: "0.75rem",
            }}
          >
            <div className="flex items-center" style={{ gap: "0.5rem" }}>
              <Download size="0.875rem" style={{ color: "var(--accent)" }} />
              <h3 style={{ fontSize: "0.875rem", fontWeight: 600, margin: 0 }}>
                {t("modal.title")}
              </h3>
              <span
                className="mono dim"
                style={{ fontSize: "0.71875rem" }}
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
            style={{ padding: "0.625rem 1.125rem", gap: "0.75rem" }}
          >
            <div
              className="flex items-center"
              style={{ gap: "0.5rem", fontSize: "0.75rem" }}
            >
              {state === "running" && (
                <>
                  <Spinner size="sm" />
                  <span>{t("status.running")}</span>
                </>
              )}
              {state === "success" && (
                <>
                  <CheckCircle2
                    size="0.875rem"
                    style={{ color: "var(--c-ok)" }}
                  />
                  <span style={{ color: "var(--c-ok)" }}>
                    {t("status.success")}
                  </span>
                </>
              )}
              {state === "failure" && (
                <>
                  <XCircle size="0.875rem" style={{ color: "var(--c-err)" }} />
                  <span style={{ color: "var(--c-err)" }}>
                    {t("status.failure")}
                  </span>
                </>
              )}
            </div>
            <div className="flex items-center" style={{ gap: "0.5rem" }}>
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
