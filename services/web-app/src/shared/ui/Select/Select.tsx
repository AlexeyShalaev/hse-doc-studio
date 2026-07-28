import * as SelectPrimitive from "@radix-ui/react-select";
import { clsx } from "clsx";
import { forwardRef } from "react";

export type SelectOption = {
  value: string;
  label: string;
  isDisabled?: boolean;
};

export type SelectProps = {
  value?: string;
  defaultValue?: string;
  onValueChange?: (value: string) => void;
  options: SelectOption[];
  placeholder?: string;
  isDisabled?: boolean;
  className?: string;
  id?: string;
  /**
   * Radix refocuses the trigger when the popup closes; callers embedding the
   * select in an editor toolbar can preventDefault here and refocus the
   * editor instead.
   */
  onCloseAutoFocus?: (event: Event) => void;
};

export const Select = forwardRef<HTMLButtonElement, SelectProps>(
  (
    {
      value,
      defaultValue,
      onValueChange,
      options,
      placeholder,
      isDisabled = false,
      className,
      id,
      onCloseAutoFocus,
    },
    ref,
  ) => {
    const rootProps: SelectPrimitive.SelectProps = {
      disabled: isDisabled,
    };
    if (value !== undefined) rootProps.value = value;
    if (defaultValue !== undefined) rootProps.defaultValue = defaultValue;
    if (onValueChange !== undefined) rootProps.onValueChange = onValueChange;

    return (
      <SelectPrimitive.Root {...rootProps}>
        <SelectPrimitive.Trigger
          ref={ref}
          id={id}
          className={clsx(
            "input flex items-center justify-between gap-2 min-w-0",
            "disabled:opacity-50 disabled:cursor-not-allowed",
            className,
          )}
          aria-label={placeholder}
        >
          <span className="truncate min-w-0 flex-1 text-left">
            <SelectPrimitive.Value placeholder={placeholder} />
          </span>
          <SelectPrimitive.Icon className="text-fg-2 shrink-0">
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
              <polyline points="6 9 12 15 18 9" />
            </svg>
          </SelectPrimitive.Icon>
        </SelectPrimitive.Trigger>
        <SelectPrimitive.Portal>
          <SelectPrimitive.Content
            className={clsx(
              "z-50 overflow-hidden rounded-r-2 border border-border bg-bg-1 shadow-elev-2",
              "animate-in fade-in-0 zoom-in-95",
            )}
            position="popper"
            sideOffset={4}
            {...(onCloseAutoFocus ? { onCloseAutoFocus } : {})}
            style={{
              // Match the trigger width and bound the height so long model
              // lists scroll instead of running off-screen.
              width: "var(--radix-select-trigger-width)",
              maxHeight:
                "min(320px, var(--radix-select-content-available-height))",
            }}
          >
            <SelectPrimitive.Viewport
              className="p-1"
              style={{ overflowY: "auto" }}
            >
              {options.map((option) => (
                <SelectPrimitive.Item
                  key={option.value}
                  value={option.value}
                  disabled={option.isDisabled === true}
                  className={clsx(
                    "relative flex cursor-pointer select-none items-center rounded-r-1 py-1.5 pl-8 pr-2 text-sm text-fg-1 outline-none",
                    // Radix highlights the active item via data-highlighted (mouse
                    // hover / keyboard), NOT :focus — keying off :focus left the
                    // list with no hover feedback, hence the "bare/standard" look.
                    "data-[highlighted]:bg-bg-hover data-[highlighted]:text-fg-0",
                    "data-[disabled]:pointer-events-none data-[disabled]:opacity-40",
                  )}
                >
                  <SelectPrimitive.ItemIndicator className="absolute left-2 flex h-3.5 w-3.5 items-center justify-center text-accent">
                    <svg
                      xmlns="http://www.w3.org/2000/svg"
                      width="12"
                      height="12"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="3"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    >
                      <polyline points="20 6 9 17 4 12" />
                    </svg>
                  </SelectPrimitive.ItemIndicator>
                  <SelectPrimitive.ItemText>
                    {option.label}
                  </SelectPrimitive.ItemText>
                </SelectPrimitive.Item>
              ))}
            </SelectPrimitive.Viewport>
          </SelectPrimitive.Content>
        </SelectPrimitive.Portal>
      </SelectPrimitive.Root>
    );
  },
);

Select.displayName = "Select";
