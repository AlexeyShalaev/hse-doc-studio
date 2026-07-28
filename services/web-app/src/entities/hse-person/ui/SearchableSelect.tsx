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
          gap: 6,
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
            size={13}
            style={{ color: "var(--fg-3)", flexShrink: 0 }}
            onClick={(e) => {
              e.stopPropagation();
              onChange("");
            }}
          />
        ) : null}
        <ChevronDown
          size={13}
          style={{ color: "var(--fg-3)", flexShrink: 0 }}
        />
      </button>

      {open && (
        <div
          style={{
            position: "absolute",
            zIndex: 20,
            top: "calc(100% + 4px)",
            left: 0,
            right: 0,
            background: "var(--bg-1)",
            border: "1px solid var(--border)",
            borderRadius: 8,
            boxShadow: "0 10px 28px rgba(0,0,0,0.22)",
            padding: 6,
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
            style={{ marginBottom: 6, fontSize: 12, width: "100%" }}
          />
          <div
            style={{
              maxHeight: 240,
              overflowY: "auto",
              display: "flex",
              flexDirection: "column",
              gap: 2,
            }}
          >
            {filtered.length === 0 ? (
              <span
                style={{
                  padding: "6px 8px",
                  fontSize: 11.5,
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
                    padding: "5px 8px",
                    borderRadius: 6,
                    fontSize: 12,
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
