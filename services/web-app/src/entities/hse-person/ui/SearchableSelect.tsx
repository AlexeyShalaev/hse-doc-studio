import { useEffect, useRef, useState } from "react";
import { ChevronDown, X } from "lucide-react";

import type { HseFacetOption } from "../api";

const MAX_RENDER = 80;

export type SearchableSelectProps = {
  value: string;
  options: HseFacetOption[];
  placeholder: string;
  emptyText: string;
  disabled?: boolean;
  onChange: (value: string) => void;
};

/**
 * A filterable single-select (combobox) for large option lists — the HSE
 * department tree has ~1500 entries, which a native <select> can't handle
 * comfortably. Type to filter; the rendered list is capped for performance.
 */
export const SearchableSelect = ({
  value,
  options,
  placeholder,
  emptyText,
  disabled,
  onChange,
}: SearchableSelectProps) => {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const wrapRef = useRef<HTMLDivElement>(null);

  const selected = options.find((o) => o.value === value);

  useEffect(() => {
    if (!open) return;
    const onDocMouseDown = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", onDocMouseDown);
    return () => {
      document.removeEventListener("mousedown", onDocMouseDown);
    };
  }, [open]);

  const q = query.trim().toLowerCase();
  const filtered = (
    q ? options.filter((o) => o.label.toLowerCase().includes(q)) : options
  ).slice(0, MAX_RENDER);

  return (
    <div ref={wrapRef} style={{ position: "relative", minWidth: 0 }}>
      <button
        type="button"
        className="input"
        disabled={disabled}
        onClick={() => {
          setOpen((v) => !v);
          setQuery("");
        }}
        style={{
          display: "flex",
          alignItems: "center",
          gap: "0.375rem",
          width: "100%",
          textAlign: "left",
          cursor: disabled ? "default" : "pointer",
        }}
      >
        <span
          style={{
            flex: 1,
            minWidth: 0,
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
            color: selected ? "var(--fg-0)" : "var(--fg-3)",
          }}
        >
          {selected ? selected.label : placeholder}
        </span>
        {selected ? (
          <X
            size="0.8125rem"
            style={{ color: "var(--fg-3)", flexShrink: 0 }}
            onClick={(e) => {
              e.stopPropagation();
              onChange("");
            }}
          />
        ) : null}
        <ChevronDown
          size="0.8125rem"
          style={{ color: "var(--fg-3)", flexShrink: 0 }}
        />
      </button>

      {open && (
        <div
          style={{
            position: "absolute",
            zIndex: 20,
            top: "calc(100% + 0.25rem)",
            left: 0,
            right: 0,
            background: "var(--bg-1)",
            border: "1px solid var(--border)",
            borderRadius: "0.5rem",
            boxShadow: "0 10px 28px rgba(0,0,0,0.22)",
            padding: "0.375rem",
          }}
        >
          <input
            className="input"
            autoFocus
            value={query}
            placeholder={placeholder}
            onChange={(e) => {
              setQuery(e.target.value);
            }}
            style={{
              marginBottom: "0.375rem",
              fontSize: "0.75rem",
              width: "100%",
            }}
          />
          <div
            style={{
              maxHeight: "15rem",
              overflowY: "auto",
              display: "flex",
              flexDirection: "column",
              gap: "0.125rem",
            }}
          >
            {filtered.length === 0 ? (
              <span
                style={{
                  padding: "0.375rem 0.5rem",
                  fontSize: "0.71875rem",
                  color: "var(--fg-3)",
                }}
              >
                {emptyText}
              </span>
            ) : (
              filtered.map((o) => (
                <button
                  key={o.value}
                  type="button"
                  onClick={() => {
                    onChange(o.value);
                    setOpen(false);
                  }}
                  style={{
                    textAlign: "left",
                    padding: "0.3125rem 0.5rem",
                    borderRadius: "0.375rem",
                    fontSize: "0.75rem",
                    cursor: "pointer",
                    background:
                      o.value === value ? "var(--bg-3)" : "transparent",
                    color: "var(--fg-1)",
                  }}
                >
                  {o.label}
                </button>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
};
