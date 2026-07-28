import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  addColumn,
  addRow,
  Button,
  Modal,
  moveColumn,
  parseEditableTable,
  removeColumn,
  removeRow,
  serializeEditableTable,
  setCellValue,
  setColumnAlign,
  setColumnLabel,
  type ColumnAlign,
  type DraftTable,
} from "@shared/ui";
import {
  canRedo,
  canUndo,
  commit,
  initHistory,
  present,
  redo,
  undo,
  type History,
} from "../lib/gridHistory";
import { applyInlineFormat } from "../lib/inlineFormat";
import { RichCell } from "./RichCell";

export type TableEditorModalProps = {
  isOpen: boolean;
  /** The raw LaTeX of a single table environment. */
  source: string;
  /** Receives the regenerated LaTeX for the whole environment. */
  onSave: (next: string) => void;
  onClose: () => void;
};

const EMPTY_DRAFT: DraftTable = {
  columns: [],
  rows: [],
  rowBreaks: [],
  rowRules: [],
  finalRule: "",
};
const CELL_BORDER = "1px solid var(--border)";
const ALIGNS: ColumnAlign[] = ["left", "center", "right"];
const ALIGN_GLYPH: Record<ColumnAlign, string> = {
  left: "⯇",
  center: "≡",
  right: "⯈",
  other: "≡",
};

const iconButtonStyle: React.CSSProperties = {
  minWidth: 22,
  height: 22,
  padding: "0 4px",
  border: "1px solid var(--border)",
  borderRadius: 5,
  background: "var(--bg-1)",
  color: "var(--fg-2)",
  fontSize: 11,
  lineHeight: 1,
  cursor: "pointer",
};

export const TableEditorModal = ({
  isOpen,
  source,
  onSave,
  onClose,
}: TableEditorModalProps) => {
  const { t } = useTranslation("sourceEdit");
  const parsed = useMemo(() => parseEditableTable(source), [source]);
  const scaffold = parsed?.scaffold ?? null;

  // The draft lives in an undo/redo history; reset on a render-phase source
  // change (React "you might not need an effect"), not inside an effect.
  const [history, setHistory] = useState<History<DraftTable>>(() =>
    initHistory(parsed?.draft ?? EMPTY_DRAFT),
  );
  const [sourceKey, setSourceKey] = useState(source);
  if (sourceKey !== source) {
    setSourceKey(source);
    setHistory(initHistory(parsed?.draft ?? EMPTY_DRAFT));
  }
  const draft = present(history);
  const columns = draft.columns.length;
  const canEditColumns = scaffold?.canEditColumns ?? false;

  const apply = (
    change: (draft: DraftTable) => DraftTable,
    key: string | null,
  ): void => {
    setHistory((h) => commit(h, change(present(h)), key));
  };

  // Ctrl/Cmd+Z undo, Ctrl/Cmd+Y (or Shift+Z) redo. Cells are contenteditable,
  // so the browser's native undo can't drive the grid.
  useEffect(() => {
    if (!isOpen) return;
    const onKey = (event: KeyboardEvent): void => {
      if (!(event.ctrlKey || event.metaKey)) return;
      // Physical code so undo/redo work under a Cyrillic layout (event.key
      // would be «я»/«н»); fall back to the character too.
      const key = event.key.toLowerCase();
      const isZ = event.code === "KeyZ" || key === "z";
      const isY = event.code === "KeyY" || key === "y";
      if (isZ && !event.shiftKey) {
        event.preventDefault();
        setHistory(undo);
      } else if (isY || (isZ && event.shiftKey)) {
        event.preventDefault();
        setHistory(redo);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
    };
  }, [isOpen]);

  const handleSave = (): void => {
    if (scaffold) onSave(serializeEditableTable(scaffold, draft));
    onClose();
  };

  const formatButton = (
    command: "bold" | "italic" | "underline",
    label: string,
    glyph: string,
    fontStyle?: React.CSSProperties,
  ): React.JSX.Element => (
    <button
      type="button"
      title={label}
      aria-label={label}
      style={{ ...iconButtonStyle, minWidth: 26, ...fontStyle }}
      onMouseDown={(event) => {
        event.preventDefault(); // keep the cell's selection
      }}
      onClick={() => {
        applyInlineFormat(command);
      }}
    >
      {glyph}
    </button>
  );

  const renderColumnHeader = (columnIndex: number): React.JSX.Element => {
    const column = draft.columns[columnIndex];
    return (
      <th
        key={columnIndex}
        style={{
          border: CELL_BORDER,
          padding: 6,
          background: "var(--bg-2)",
          verticalAlign: "top",
        }}
      >
        <input
          value={column?.label ?? ""}
          disabled={!canEditColumns}
          placeholder={`${t("tableEditor.column")} ${String(columnIndex + 1)}`}
          aria-label={`${t("tableEditor.columnLabel")} ${String(columnIndex + 1)}`}
          onChange={(event) => {
            apply(
              (d) => setColumnLabel(d, columnIndex, event.target.value),
              `label:${String(columnIndex)}`,
            );
          }}
          style={{
            boxSizing: "border-box",
            width: "100%",
            marginBottom: 5,
            padding: "3px 5px",
            border: "1px solid var(--border)",
            borderRadius: 5,
            background: "var(--bg-1)",
            color: "var(--fg-0)",
            fontFamily: "var(--font-sans)",
            fontSize: 12,
            fontWeight: 600,
          }}
        />
        <div style={{ display: "flex", gap: 3, flexWrap: "wrap" }}>
          {ALIGNS.map((align) => (
            <button
              key={align}
              type="button"
              title={t(`tableEditor.align.${align}`)}
              aria-label={t(`tableEditor.align.${align}`)}
              aria-pressed={column?.align === align}
              onClick={() => {
                apply((d) => setColumnAlign(d, columnIndex, align), null);
              }}
              style={{
                ...iconButtonStyle,
                ...(column?.align === align
                  ? {
                      borderColor: "var(--accent-line)",
                      background: "var(--accent-soft)",
                      color: "var(--accent)",
                    }
                  : {}),
              }}
            >
              {ALIGN_GLYPH[align]}
            </button>
          ))}
          <button
            type="button"
            title={t("tableEditor.moveLeft")}
            aria-label={t("tableEditor.moveLeft")}
            disabled={!canEditColumns || columnIndex === 0}
            onClick={() => {
              apply((d) => moveColumn(d, columnIndex, columnIndex - 1), null);
            }}
            style={iconButtonStyle}
          >
            ‹
          </button>
          <button
            type="button"
            title={t("tableEditor.moveRight")}
            aria-label={t("tableEditor.moveRight")}
            disabled={!canEditColumns || columnIndex === columns - 1}
            onClick={() => {
              apply((d) => moveColumn(d, columnIndex, columnIndex + 1), null);
            }}
            style={iconButtonStyle}
          >
            ›
          </button>
          <button
            type="button"
            title={t("tableEditor.deleteColumn")}
            aria-label={t("tableEditor.deleteColumn")}
            disabled={
              !canEditColumns || columns <= 1 || (column?.isIdColumn ?? false)
            }
            onClick={() => {
              apply((d) => removeColumn(d, columnIndex), null);
            }}
            style={{ ...iconButtonStyle, color: "var(--fg-3)" }}
          >
            ✕
          </button>
        </div>
      </th>
    );
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={t("tableEditor.title")}
      description={t("tableEditor.description")}
      width={Math.min(1040, 210 * Math.max(columns, 2) + 200)}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            {t("tableEditor.cancel")}
          </Button>
          <Button variant="primary" onClick={handleSave} disabled={!scaffold}>
            {t("tableEditor.save")}
          </Button>
        </>
      }
    >
      {!scaffold ? (
        <p style={{ margin: 0, color: "var(--fg-2)", fontSize: 13 }}>
          {t("tableEditor.unsupported")}
        </p>
      ) : (
        <div style={{ maxHeight: "62vh", overflow: "auto" }}>
          <div
            style={{
              position: "sticky",
              top: 0,
              zIndex: 1,
              display: "flex",
              alignItems: "center",
              gap: 8,
              marginBottom: 10,
              paddingBottom: 8,
              borderBottom: CELL_BORDER,
              background: "var(--bg-1)",
            }}
          >
            <button
              type="button"
              title={t("tableEditor.undo")}
              aria-label={t("tableEditor.undo")}
              disabled={!canUndo(history)}
              onClick={() => {
                setHistory(undo);
              }}
              style={iconButtonStyle}
            >
              ↶
            </button>
            <button
              type="button"
              title={t("tableEditor.redo")}
              aria-label={t("tableEditor.redo")}
              disabled={!canRedo(history)}
              onClick={() => {
                setHistory(redo);
              }}
              style={iconButtonStyle}
            >
              ↷
            </button>
            <span
              style={{ width: 1, height: 18, background: "var(--border)" }}
            />
            {formatButton("bold", t("tableEditor.bold"), "Ж", {
              fontWeight: 700,
            })}
            {formatButton("italic", t("tableEditor.italic"), "К", {
              fontStyle: "italic",
            })}
            {formatButton("underline", t("tableEditor.underline"), "Ч", {
              textDecoration: "underline",
            })}
          </div>

          <table
            style={{
              width: "100%",
              borderCollapse: "collapse",
              tableLayout: "fixed",
            }}
          >
            <thead>
              <tr>
                {draft.columns.map((_, columnIndex) =>
                  renderColumnHeader(columnIndex),
                )}
                <th
                  style={{
                    width: 34,
                    border: CELL_BORDER,
                    background: "var(--bg-2)",
                    verticalAlign: "top",
                    padding: 4,
                  }}
                >
                  <button
                    type="button"
                    title={t("tableEditor.addColumn")}
                    aria-label={t("tableEditor.addColumn")}
                    disabled={!canEditColumns}
                    onClick={() => {
                      apply((d) => addColumn(d, d.columns.length), null);
                    }}
                    style={iconButtonStyle}
                  >
                    ＋
                  </button>
                </th>
              </tr>
            </thead>
            <tbody>
              {draft.rows.map((row, rowIndex) => (
                <tr key={rowIndex}>
                  {row.map((cell, columnIndex) => (
                    <td
                      key={columnIndex}
                      style={{ border: CELL_BORDER, verticalAlign: "top" }}
                    >
                      <RichCell
                        value={cell.value}
                        ariaLabel={`${draft.columns[columnIndex]?.label ?? ""} — ${String(rowIndex + 1)}`}
                        onChange={(value) => {
                          apply(
                            (d) =>
                              setCellValue(d, rowIndex, columnIndex, value),
                            `cell:${String(rowIndex)}:${String(columnIndex)}`,
                          );
                        }}
                      />
                    </td>
                  ))}
                  <td
                    style={{
                      border: CELL_BORDER,
                      textAlign: "center",
                      verticalAlign: "middle",
                    }}
                  >
                    <button
                      type="button"
                      title={t("tableEditor.deleteRow")}
                      aria-label={t("tableEditor.deleteRow")}
                      onClick={() => {
                        apply((d) => removeRow(d, rowIndex), null);
                      }}
                      style={{ ...iconButtonStyle, color: "var(--fg-3)" }}
                    >
                      ✕
                    </button>
                  </td>
                </tr>
              ))}
              {draft.rows.length === 0 && (
                <tr>
                  <td
                    colSpan={columns + 1}
                    style={{
                      border: CELL_BORDER,
                      padding: "16px 8px",
                      color: "var(--fg-3)",
                      fontFamily: "var(--font-sans)",
                      fontSize: 12,
                      fontStyle: "italic",
                      textAlign: "center",
                    }}
                  >
                    {t("tableEditor.empty")}
                  </td>
                </tr>
              )}
            </tbody>
          </table>

          <button
            type="button"
            onClick={() => {
              apply(addRow, null);
            }}
            style={{
              marginTop: 12,
              padding: "6px 12px",
              border: "1px dashed var(--accent-line)",
              borderRadius: 7,
              background: "var(--accent-soft)",
              color: "var(--accent)",
              fontFamily: "var(--font-sans)",
              fontSize: 12,
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            + {t("tableEditor.addRow")}
          </button>
          {!canEditColumns && (
            <p
              style={{
                margin: "10px 0 0",
                color: "var(--fg-3)",
                fontSize: 11,
                fontStyle: "italic",
              }}
            >
              {t("tableEditor.columnsLocked")}
            </p>
          )}
        </div>
      )}
    </Modal>
  );
};

TableEditorModal.displayName = "TableEditorModal";
