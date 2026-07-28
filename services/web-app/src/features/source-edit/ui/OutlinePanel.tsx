import { ListTree, Search, X } from "lucide-react";
import { clsx } from "clsx";
import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import type { OutlineState } from "@shared/ui";

export type OutlinePanelProps = {
  outline: OutlineState | null;
  /** Jump to a 1-based line (the editor's reveal mechanism). */
  onSelect: (line: number) => void;
  onClose: () => void;
};

/**
 * Searchable Word-style navigation pane. It becomes an overlay when the editor
 * is narrow, so opening the outline never crushes the writing column.
 */
export const OutlinePanel = ({
  outline,
  onSelect,
  onClose,
}: OutlinePanelProps) => {
  const { t } = useTranslation("sourceEdit");
  const [query, setQuery] = useState("");
  const activeRef = useRef<HTMLButtonElement | null>(null);
  const items = useMemo(() => outline?.items ?? [], [outline?.items]);
  const normalizedQuery = query.trim().toLocaleLowerCase();
  const visibleItems = useMemo(
    () =>
      items
        .map((item, index) => ({ item, index }))
        .filter(({ item }) =>
          normalizedQuery
            ? item.title.toLocaleLowerCase().includes(normalizedQuery)
            : true,
        ),
    [items, normalizedQuery],
  );

  // Keep the active section visible while the user moves through the doc.
  useEffect(() => {
    activeRef.current?.scrollIntoView({ block: "nearest" });
  }, [outline?.activeIndex, normalizedQuery]);

  const activePosition =
    (outline?.activeIndex ?? -1) >= 0 ? (outline?.activeIndex ?? -1) + 1 : 0;

  return (
    <nav className="visual-outline-panel" aria-label={t("outline.title")}>
      <div className="visual-outline-header">
        <span className="visual-outline-title">
          <ListTree size={14} />
          {t("outline.title")}
        </span>
        <span className="visual-outline-progress">
          {activePosition > 0
            ? t("outline.progress", {
                current: activePosition,
                total: items.length,
              })
            : t("outline.total", { count: items.length })}
        </span>
        <button
          type="button"
          className="icon-btn sm tt visual-outline-close"
          data-tt={t("outline.close")}
          aria-label={t("outline.close")}
          onClick={onClose}
        >
          <X size={13} />
        </button>
      </div>

      {items.length > 0 && (
        <label className="visual-outline-search">
          <Search size={13} aria-hidden="true" />
          <input
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
            }}
            placeholder={t("outline.searchPlaceholder")}
            aria-label={t("outline.searchLabel")}
          />
          {query && (
            <button
              type="button"
              aria-label={t("outline.clearSearch")}
              onClick={() => {
                setQuery("");
              }}
            >
              <X size={12} />
            </button>
          )}
        </label>
      )}

      <div className="visual-outline-list">
        {items.length === 0 && (
          <div className="visual-outline-empty">{t("outline.empty")}</div>
        )}
        {items.length > 0 && visibleItems.length === 0 && (
          <div className="visual-outline-empty">
            {t("outline.noResults", { query })}
          </div>
        )}
        {visibleItems.map(({ item, index }) => {
          const active = index === outline?.activeIndex;
          return (
            <button
              key={String(item.from) + "-" + item.title}
              ref={active ? activeRef : null}
              type="button"
              className={clsx("visual-outline-item", active && "active")}
              aria-current={active ? "location" : undefined}
              onClick={() => {
                onSelect(item.line);
              }}
              title={item.title}
              style={
                {
                  "--outline-indent": `${String((item.level - 1) * 11)}px`,
                } as React.CSSProperties
              }
            >
              <span className="visual-outline-marker" aria-hidden="true" />
              <span>{item.title}</span>
            </button>
          );
        })}
      </div>
    </nav>
  );
};
