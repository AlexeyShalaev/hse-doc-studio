import { useEffect, useRef, useState } from "react";
import { Check, Copy } from "lucide-react";
import { clsx } from "clsx";
import { useTranslation } from "react-i18next";

// Read-only monospace value with a copy button (public SSH key, fingerprint, a
// command). The result of the copy is announced through a polite live region
// and shown on the button, so it works for keyboard and screen-reader users.

export type CopyFieldProps = {
  value: string;
  /** Accessible name of the value, e.g. "Public key". */
  label: string;
  /** Show the whole value on several lines (keys, commands) instead of one. */
  multiline?: boolean;
  /** Called after the value reached the clipboard. */
  onCopied?: () => void;
  className?: string;
};

type CopyState = "idle" | "copied" | "failed";

const RESET_MS = 2000;

export const CopyField = ({
  value,
  label,
  multiline = false,
  onCopied,
  className,
}: CopyFieldProps) => {
  const { t } = useTranslation("uiPrimitives");
  const [state, setState] = useState<CopyState>("idle");
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const field = useRef<HTMLInputElement & HTMLTextAreaElement>(null);

  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current);
    },
    [],
  );

  const settle = (next: CopyState): void => {
    setState(next);
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      setState("idle");
    }, RESET_MS);
  };

  const handleCopy = async (): Promise<void> => {
    try {
      await navigator.clipboard.writeText(value);
      settle("copied");
      onCopied?.();
    } catch {
      // No clipboard permission (insecure origin, blocked): select the text so
      // the user can copy it by hand.
      field.current?.select();
      settle("failed");
    }
  };

  const Field = multiline ? "textarea" : "input";
  return (
    <div
      className={clsx("flex", className)}
      style={{ gap: 6, alignItems: multiline ? "flex-start" : "stretch" }}
    >
      <Field
        ref={field}
        readOnly
        value={value}
        aria-label={label}
        className="input mono"
        onFocus={(event) => {
          event.currentTarget.select();
        }}
        style={{
          flex: 1,
          minWidth: 0,
          fontSize: 11.5,
          ...(multiline
            ? {
                resize: "none",
                minHeight: 72,
                lineHeight: 1.45,
                wordBreak: "break-all",
              }
            : { textOverflow: "ellipsis" }),
        }}
        {...(multiline ? { rows: 3 } : {})}
      />
      <button
        type="button"
        className="btn"
        onClick={() => void handleCopy()}
        style={{ flexShrink: 0, ...(multiline ? {} : { height: "auto" }) }}
        data-state={state}
      >
        {state === "copied" ? (
          <Check
            size={13}
            style={{ color: "var(--c-ok)" }}
            aria-hidden="true"
          />
        ) : (
          <Copy size={13} aria-hidden="true" />
        )}
        {state === "copied" ? t("copyField.copied") : t("copyField.copy")}
      </button>
      <span role="status" aria-live="polite" className="sr-only">
        {state === "copied"
          ? t("copyField.copiedAnnounce", { label })
          : state === "failed"
            ? t("copyField.failed")
            : ""}
      </span>
    </div>
  );
};

CopyField.displayName = "CopyField";
