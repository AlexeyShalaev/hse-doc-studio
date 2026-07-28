import { forwardRef } from "react";
import { clsx } from "clsx";

export type TextareaProps =
  React.TextareaHTMLAttributes<HTMLTextAreaElement> & {
    label?: string;
    error?: string;
    id?: string;
    hint?: string;
    isMono?: boolean;
  };

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ className, label, error, id, hint, isMono, ...props }, ref) => {
    const textareaId = id ?? label?.toLowerCase().replace(/\s+/g, "-");
    return (
      <div className="field">
        {label && <label htmlFor={textareaId}>{label}</label>}
        <textarea
          ref={ref}
          id={textareaId}
          className={clsx(
            "textarea",
            isMono && "mono",
            error && "!border-c-err",
            className,
          )}
          {...props}
        />
        {error && (
          <p className="text-xs text-c-err" role="alert">
            {error}
          </p>
        )}
        {hint && !error && <p className="hint">{hint}</p>}
      </div>
    );
  },
);

Textarea.displayName = "Textarea";
