import { forwardRef, useId } from "react";
import { clsx } from "clsx";

export type InputProps = React.InputHTMLAttributes<HTMLInputElement> & {
  label?: string;
  error?: string;
  id?: string;
  hint?: string;
  isMono?: boolean;
};

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ className, label, error, id, hint, isMono, ...props }, ref) => {
    const inputId = id ?? label?.toLowerCase().replace(/\s+/g, "-");
    const uid = useId();
    const errorId = `${uid}-error`;
    const hintId = `${uid}-hint`;
    // Ошибка и подсказка связаны с полем: скринридер читает их вместе с меткой.
    const describedBy =
      [props["aria-describedby"], error ? errorId : hint ? hintId : undefined]
        .filter(Boolean)
        .join(" ") || undefined;
    return (
      <div className="field">
        {label && <label htmlFor={inputId}>{label}</label>}
        <input
          ref={ref}
          id={inputId}
          className={clsx(
            "input",
            isMono && "mono",
            error && "!border-c-err",
            className,
          )}
          {...props}
          aria-invalid={error ? true : props["aria-invalid"]}
          aria-describedby={describedBy}
        />
        {error && (
          <p id={errorId} className="text-xs text-c-err" role="alert">
            {error}
          </p>
        )}
        {hint && !error && (
          <p id={hintId} className="hint">
            {hint}
          </p>
        )}
      </div>
    );
  },
);

Input.displayName = "Input";
