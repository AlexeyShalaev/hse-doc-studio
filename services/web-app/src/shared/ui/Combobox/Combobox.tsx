import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
import { createPortal } from "react-dom";
import { Command } from "cmdk";
import { Check, ChevronDown } from "lucide-react";
import { clsx } from "clsx";
import { useTranslation } from "react-i18next";

export type ComboboxOption = {
  value: string;
  label: string;
};

export type ComboboxProps = {
  value?: string;
  onValueChange?: (value: string) => void;
  options: ComboboxOption[];
  placeholder?: string;
  searchPlaceholder?: string;
  emptyText?: string;
  disabled?: boolean;
  placement?: "bottom" | "top";
  className?: string;
  id?: string;
};

type Rect = {
  left: number;
  top: number;
  width: number;
  transform: string;
};

/**
 * A searchable select (combobox): a field that opens a filterable, scrollable
 * list. Built on cmdk for fuzzy filtering + keyboard nav; positioned via a
 * fixed portal so it escapes any scrolling/overflow-hidden parent. Styled with
 * the app's design tokens (see `.combo-*` in index.css), not raw Tailwind.
 */
export const Combobox = ({
  value,
  onValueChange,
  options,
  placeholder,
  searchPlaceholder,
  emptyText,
  disabled = false,
  placement = "bottom",
  className,
  id,
}: ComboboxProps) => {
  const { t } = useTranslation("uiPrimitives");
  const placeholderText = placeholder ?? t("combobox.selectPlaceholder");
  const searchPlaceholderText =
    searchPlaceholder ?? t("combobox.searchPlaceholder");
  const emptyTextLabel = emptyText ?? t("combobox.emptyText");
  const [open, setOpen] = useState(false);
  const [rect, setRect] = useState<Rect | null>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  const selected = options.find((o) => o.value === value);

  const place = useCallback(() => {
    const el = triggerRef.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    setRect({
      left: r.left,
      top: placement === "top" ? r.top - 4 : r.bottom + 4,
      width: r.width,
      transform: placement === "top" ? "translateY(-100%)" : "none",
    });
  }, [placement]);

  useLayoutEffect(() => {
    if (open) place();
  }, [open, place]);

  useEffect(() => {
    if (!open) return undefined;
    const reposition = () => {
      place();
    };
    const onPointerDown = (e: MouseEvent) => {
      const target = e.target as Node;
      if (
        triggerRef.current?.contains(target) ||
        panelRef.current?.contains(target)
      )
        return;
      setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("resize", reposition);
    window.addEventListener("scroll", reposition, true);
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("resize", reposition);
      window.removeEventListener("scroll", reposition, true);
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open, place]);

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        id={id}
        disabled={disabled}
        className={clsx(
          "input flex items-center justify-between gap-2 min-w-0",
          "disabled:opacity-50 disabled:cursor-not-allowed",
          className,
        )}
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => {
          if (!disabled) setOpen((o) => !o);
        }}
      >
        <span
          className={clsx(
            "truncate min-w-0 flex-1 text-left",
            !selected && "dim",
          )}
        >
          {selected ? selected.label : placeholderText}
        </span>
        <ChevronDown
          size={14}
          className="shrink-0"
          style={{ color: "var(--fg-2)" }}
        />
      </button>

      {open &&
        rect &&
        createPortal(
          <div
            ref={panelRef}
            className="combo-menu"
            style={{
              position: "fixed",
              left: rect.left,
              top: rect.top,
              width: rect.width,
              transform: rect.transform,
              zIndex: 200,
            }}
          >
            <Command loop>
              <Command.Input
                className="combo-input"
                placeholder={searchPlaceholderText}
                autoFocus
              />
              <Command.List className="combo-list">
                <Command.Empty className="combo-empty">
                  {emptyTextLabel}
                </Command.Empty>
                {options.map((option) => (
                  <Command.Item
                    key={option.value}
                    value={option.label}
                    className="combo-item"
                    onSelect={() => {
                      onValueChange?.(option.value);
                      setOpen(false);
                    }}
                  >
                    <Check
                      size={13}
                      className="combo-check"
                      style={{ opacity: option.value === value ? 1 : 0 }}
                    />
                    <span className="truncate">{option.label}</span>
                  </Command.Item>
                ))}
              </Command.List>
            </Command>
          </div>,
          document.body,
        )}
    </>
  );
};
