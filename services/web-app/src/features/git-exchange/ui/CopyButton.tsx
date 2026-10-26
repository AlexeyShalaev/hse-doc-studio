import { useEffect, useRef, useState } from "react";
import { Check, Copy } from "lucide-react";
import { useTranslation } from "react-i18next";

export type CopyButtonProps = {
  value: string;
  label: string;
};

type CopyState = "idle" | "copied" | "failed";

// Кнопка «Копировать» для текста, который не помещается в строку (файл целиком).
// Итог слышит и скринридер.
export const CopyButton = ({ value, label }: CopyButtonProps) => {
  const { t } = useTranslation("gitExchange");
  const [state, setState] = useState<CopyState>("idle");
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

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
    }, 2000);
  };

  const copy = async (): Promise<void> => {
    try {
      await navigator.clipboard.writeText(value);
      settle("copied");
    } catch {
      settle("failed");
    }
  };

  return (
    <>
      <button
        type="button"
        className="btn xs"
        aria-label={label}
        title={label}
        onClick={() => {
          void copy();
        }}
      >
        {state === "copied" ? (
          <Check size={12} aria-hidden="true" />
        ) : (
          <Copy size={12} aria-hidden="true" />
        )}
      </button>
      <span
        role="status"
        aria-live="polite"
        style={{
          position: "absolute",
          width: 1,
          height: 1,
          overflow: "hidden",
          clip: "rect(0 0 0 0)",
        }}
      >
        {state === "copied" && t("ci.preview.copied")}
        {state === "failed" && t("ci.preview.copyFailed")}
      </span>
    </>
  );
};
