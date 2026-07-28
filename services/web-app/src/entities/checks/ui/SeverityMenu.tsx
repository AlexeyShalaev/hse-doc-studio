import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { Check, ChevronDown, RotateCcw } from "lucide-react";
import { clsx } from "clsx";
import { useTranslation } from "react-i18next";
import type { CheckSeverity } from "@shared/api/types";
import type { Severity } from "../types";

const SEVERITY_OPTIONS: { value: CheckSeverity; label: string }[] = [
  { value: "err", label: "ERR" },
  { value: "warn", label: "WARN" },
  { value: "info", label: "INFO" },
];

export type SeverityMenuProps = {
  severity: Severity;
  isOverridden: boolean;
  disabled: boolean;
  onSet: (sev: CheckSeverity) => void;
  onReset: () => void;
};

// Clickable severity chip. Opens a dropdown to change severity (per-document
// override, persisted in checks_override.severity_override) or reset to the
// rule's default. Visual cues: dot indicator when the rule is overridden.
export const SeverityMenu = ({
  severity,
  isOverridden,
  disabled,
  onSet,
  onReset,
}: SeverityMenuProps) => {
  const { t } = useTranslation("checks");
  // "ok" is a result-status, not a severity user can set — show it as info-colored.
  const sevForChip = severity === "ok" ? "info" : severity;
  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger asChild>
        <button
          type="button"
          disabled={disabled}
          className={clsx("sev shrink-0", sevForChip)}
          style={{
            minWidth: 60,
            justifyContent: "center",
            gap: 4,
            cursor: disabled ? "not-allowed" : "pointer",
            position: "relative",
          }}
          title={t("severity.menuTitle")}
        >
          {severity.toUpperCase()}
          <ChevronDown size={9} style={{ opacity: 0.7 }} />
          {isOverridden && (
            <span
              style={{
                position: "absolute",
                top: -2,
                right: -2,
                width: 5,
                height: 5,
                borderRadius: "50%",
                background: "var(--accent)",
                boxShadow: "0 0 0 1.5px var(--bg-1)",
              }}
              aria-label={t("severity.overriddenAria")}
            />
          )}
        </button>
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content
          className={clsx(
            "z-50 min-w-[8rem] overflow-hidden rounded-r-2 border border-border bg-bg-1",
            "shadow-elev-pop",
            "data-[state=open]:animate-in data-[state=open]:fade-in-0",
            "data-[state=open]:zoom-in-95 origin-top",
          )}
          sideOffset={4}
          align="start"
        >
          <div
            className="label-up dimmer"
            style={{
              padding: "6px 10px 4px",
              fontSize: 9.5,
              letterSpacing: "0.1em",
            }}
          >
            {t("severity.header")}
          </div>
          <div className="divider" />
          {SEVERITY_OPTIONS.map((opt) => (
            <DropdownMenu.Item
              key={opt.value}
              className={clsx(
                "flex cursor-pointer select-none items-center gap-2 outline-none",
                "focus:bg-bg-hover",
              )}
              style={{ padding: "7px 10px", fontSize: 12 }}
              onSelect={() => {
                onSet(opt.value);
              }}
            >
              <span
                className={"sev " + opt.value}
                style={{ minWidth: 48, justifyContent: "center" }}
              >
                {opt.label}
              </span>
              {severity === opt.value && (
                <Check size={11} className="ml-auto text-accent" />
              )}
            </DropdownMenu.Item>
          ))}
          {isOverridden && (
            <>
              <div className="divider" />
              <DropdownMenu.Item
                className={clsx(
                  "flex cursor-pointer select-none items-center gap-2 outline-none",
                  "focus:bg-bg-hover",
                )}
                style={{ padding: "7px 10px", fontSize: 12 }}
                onSelect={() => {
                  onReset();
                }}
              >
                <RotateCcw size={11} className="text-fg-3" />
                <span>{t("common:actions.reset")}</span>
              </DropdownMenu.Item>
            </>
          )}
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
};
