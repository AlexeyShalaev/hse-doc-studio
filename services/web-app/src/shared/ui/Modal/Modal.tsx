import * as DialogPrimitive from "@radix-ui/react-dialog";
import { clsx } from "clsx";
import { useTranslation } from "react-i18next";

export type ModalProps = {
  isOpen: boolean;
  onClose: () => void;
  title?: React.ReactNode;
  description?: React.ReactNode;
  children?: React.ReactNode;
  footer?: React.ReactNode;
  className?: string;
  // Panel width in px. Sized via inline style (not Tailwind max-w-*) to match
  // the other modals in this app — the Tailwind width utilities aren't reliable
  // here, so `w-full` alone would stretch the panel to the full viewport.
  width?: number;
};

export const Modal = ({
  isOpen,
  onClose,
  title,
  description,
  children,
  footer,
  className,
  width = 480,
}: ModalProps) => {
  const { t } = useTranslation("uiPrimitives");
  return (
    <DialogPrimitive.Root
      open={isOpen}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay
          className={clsx(
            "scrim",
            "animate-in fade-in-0 data-[state=closed]:animate-out data-[state=closed]:fade-out-0",
          )}
        />
        <DialogPrimitive.Content
          className={clsx(
            "modal-panel fixed left-1/2 top-1/2 z-[101] -translate-x-1/2 -translate-y-1/2",
            "animate-in fade-in-0 zoom-in-95",
            "data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-95",
            className,
          )}
          // Spacing is inline (not Tailwind p-*/m-*) for the same reason as the
          // width — the utilities aren't reliably generated for this component.
          style={{ width, maxWidth: "calc(100vw - 32px)", padding: 24 }}
        >
          {title && (
            <DialogPrimitive.Title
              style={{
                margin: 0,
                paddingRight: 28,
                fontSize: 15,
                fontWeight: 600,
                color: "var(--fg-0)",
              }}
            >
              {title}
            </DialogPrimitive.Title>
          )}
          {description && (
            <DialogPrimitive.Description
              style={{
                marginTop: title ? 8 : 0,
                marginBottom: 0,
                fontSize: 13,
                lineHeight: 1.5,
                color: "var(--fg-2)",
              }}
            >
              {description}
            </DialogPrimitive.Description>
          )}
          {children != null && <div style={{ marginTop: 16 }}>{children}</div>}
          {footer && (
            <div
              style={{
                marginTop: 20,
                display: "flex",
                alignItems: "center",
                justifyContent: "flex-end",
                gap: 10,
              }}
            >
              {footer}
            </div>
          )}
          <DialogPrimitive.Close
            className="icon-btn"
            aria-label={t("modal.close")}
            style={{ position: "absolute", right: 12, top: 12 }}
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </DialogPrimitive.Close>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
};

Modal.displayName = "Modal";
