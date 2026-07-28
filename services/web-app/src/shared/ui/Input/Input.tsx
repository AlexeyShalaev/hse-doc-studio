import { forwardRef } from "react";
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

Input.displayName = "Input";
