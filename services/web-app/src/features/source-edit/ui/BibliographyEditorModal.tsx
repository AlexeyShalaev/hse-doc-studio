import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  addEntry,
  Button,
  hasEmptyKey,
  Modal,
  moveEntry,
  parseEditableBibliography,
  removeEntry,
  sanitizeKey,
  serializeEditableBibliography,
  setEntryKey,
  setEntryValue,
  type BibliographyDraft,
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

export type BibliographyEditorModalProps = {
  isOpen: boolean;
  /** The raw LaTeX of a single `thebibliography` environment. */
  source: string;
  /** Receives the regenerated LaTeX for the whole environment. */
  onSave: (next: string) => void;
  onClose: () => void;
};

const EMPTY_DRAFT: BibliographyDraft = { entries: [] };
const CARD_BORDER = "1px solid var(--border)";

const iconButtonStyle: React.CSSProperties = {
  minWidth: 24,
  height: 24,
  padding: "0 5px",
  border: "1px solid var(--border)",
  borderRadius: 5,
  background: "var(--bg-1)",
  color: "var(--fg-2)",
  fontSize: 12,
  lineHeight: 1,
  cursor: "pointer",
};

export const BibliographyEditorModal = ({
  isOpen,
  source,
  onSave,
  onClose,
}: BibliographyEditorModalProps) => {
  const { t } = useTranslation("sourceEdit");
  const parsed = useMemo(() => parseEditableBibliography(source), [source]);
  const scaffold = parsed?.scaffold ?? null;

  // The draft lives in an undo/redo history; reset on a render-phase source
  // change (React "you might not need an effect"), not inside an effect.
  const [history, setHistory] = useState<History<BibliographyDraft>>(() =>
    initHistory(parsed?.draft ?? EMPTY_DRAFT),
  );
  const [sourceKey, setSourceKey] = useState(source);
  if (sourceKey !== source) {
    setSourceKey(source);
    setHistory(initHistory(parsed?.draft ?? EMPTY_DRAFT));
  }
  const draft = present(history);
  const count = draft.entries.length;
  const blockedByKey = hasEmptyKey(draft);

  const apply = (
    change: (draft: BibliographyDraft) => BibliographyDraft,
    key: string | null,
  ): void => {
    setHistory((h) => commit(h, change(present(h)), key));
  };

  // Ctrl/Cmd+Z undo, Ctrl/Cmd+Y (or Shift+Z) redo — the key/text fields are
  // controlled, so the browser's native undo can't drive the list.
  useEffect(() => {
    if (!isOpen) return;
    const onKey = (event: KeyboardEvent): void => {
      if (!(event.ctrlKey || event.metaKey)) return;
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
    if (!scaffold || blockedByKey) return;
    onSave(serializeEditableBibliography(scaffold, draft));
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
      style={{ ...iconButtonStyle, minWidth: 28, ...fontStyle }}
      onMouseDown={(event) => {
        event.preventDefault(); // keep the focused cell's selection
      }}
      onClick={() => {
        applyInlineFormat(command);
      }}
    >
      {glyph}
    </button>
  );

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={t("bibliographyEditor.title")}
      description={t("bibliographyEditor.description")}
      width={760}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            {t("bibliographyEditor.cancel")}
          </Button>
          <Button
            variant="primary"
            onClick={handleSave}
            disabled={!scaffold || blockedByKey}
            {...(blockedByKey
              ? { title: t("bibliographyEditor.emptyKeyBlocked") }
              : {})}
          >
            {t("bibliographyEditor.save")}
          </Button>
        </>
      }
    >
      {!scaffold ? (
        <p style={{ margin: 0, color: "var(--fg-2)", fontSize: 13 }}>
          {t("bibliographyEditor.unsupported")}
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
              marginBottom: 12,
              paddingBottom: 8,
              borderBottom: CARD_BORDER,
              background: "var(--bg-1)",
            }}
          >
            <button
              type="button"
              title={t("bibliographyEditor.undo")}
              aria-label={t("bibliographyEditor.undo")}
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
              title={t("bibliographyEditor.redo")}
              aria-label={t("bibliographyEditor.redo")}
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
            {formatButton("bold", t("bibliographyEditor.bold"), "Ж", {
              fontWeight: 700,
            })}
            {formatButton("italic", t("bibliographyEditor.italic"), "К", {
              fontStyle: "italic",
            })}
            {formatButton("underline", t("bibliographyEditor.underline"), "Ч", {
              textDecoration: "underline",
            })}
            <span
              style={{
                marginLeft: "auto",
                color: "var(--fg-3)",
                fontSize: 12,
              }}
            >
              {t("bibliographyEditor.count", { count })}
            </span>
          </div>

          <ol
            style={{
              listStyle: "none",
              margin: 0,
              padding: 0,
              display: "flex",
              flexDirection: "column",
              gap: 10,
            }}
          >
            {draft.entries.map((entry, index) => (
              <li
                key={index}
                style={{
                  display: "grid",
                  gridTemplateColumns: "26px 1fr auto",
                  gap: 8,
                  alignItems: "start",
                  padding: 10,
                  border: CARD_BORDER,
                  borderRadius: 8,
                  background: "var(--bg-0)",
                }}
              >
                <span
                  style={{
                    fontVariantNumeric: "tabular-nums",
                    fontWeight: 700,
                    color: "var(--accent)",
                    paddingTop: 5,
                  }}
                >
                  {index + 1}.
                </span>
                <div
                  style={{ display: "flex", flexDirection: "column", gap: 6 }}
                >
                  <label
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 6,
                      fontSize: 12,
                      color: "var(--fg-3)",
                    }}
                  >
                    <span style={{ minWidth: 34 }}>
                      {t("bibliographyEditor.key")}
                    </span>
                    <input
                      value={entry.key}
                      placeholder={t("bibliographyEditor.keyPlaceholder")}
                      aria-label={`${t("bibliographyEditor.key")} ${String(index + 1)}`}
                      onChange={(event) => {
                        // Strip characters that would break the `{key}` group or
                        // a `\cite` key, so the field always holds a valid key.
                        apply(
                          (d) =>
                            setEntryKey(
                              d,
                              index,
                              sanitizeKey(event.target.value),
                            ),
                          `key:${String(index)}`,
                        );
                      }}
                      style={{
                        boxSizing: "border-box",
                        flex: 1,
                        padding: "3px 6px",
                        border: `1px solid ${
                          entry.key.trim() === ""
                            ? "var(--danger, var(--accent-line))"
                            : "var(--border)"
                        }`,
                        borderRadius: 5,
                        background: "var(--bg-1)",
                        color: "var(--fg-0)",
                        fontFamily: "var(--font-mono)",
                        fontSize: 12,
                      }}
                    />
                  </label>
                  <RichCell
                    value={entry.value}
                    ariaLabel={`${t("bibliographyEditor.text")} ${String(index + 1)}`}
                    onChange={(value) => {
                      apply(
                        (d) => setEntryValue(d, index, value),
                        `val:${String(index)}`,
                      );
                    }}
                  />
                </div>
                <div
                  style={{ display: "flex", flexDirection: "column", gap: 4 }}
                >
                  <button
                    type="button"
                    title={t("bibliographyEditor.moveUp")}
                    aria-label={t("bibliographyEditor.moveUp")}
                    disabled={index === 0}
                    onClick={() => {
                      apply((d) => moveEntry(d, index, index - 1), null);
                    }}
                    style={iconButtonStyle}
                  >
                    ↑
                  </button>
                  <button
                    type="button"
                    title={t("bibliographyEditor.moveDown")}
                    aria-label={t("bibliographyEditor.moveDown")}
                    disabled={index === count - 1}
                    onClick={() => {
                      apply((d) => moveEntry(d, index, index + 1), null);
                    }}
                    style={iconButtonStyle}
                  >
                    ↓
                  </button>
                  <button
                    type="button"
                    title={t("bibliographyEditor.delete")}
                    aria-label={t("bibliographyEditor.delete")}
                    onClick={() => {
                      apply((d) => removeEntry(d, index), null);
                    }}
                    style={{ ...iconButtonStyle, color: "var(--fg-3)" }}
                  >
                    ✕
                  </button>
                </div>
              </li>
            ))}
            {count === 0 && (
              <li
                style={{
                  border: CARD_BORDER,
                  borderRadius: 8,
                  padding: "16px 8px",
                  color: "var(--fg-3)",
                  fontSize: 12,
                  fontStyle: "italic",
                  textAlign: "center",
                }}
              >
                {t("bibliographyEditor.empty")}
              </li>
            )}
          </ol>

          <button
            type="button"
            onClick={() => {
              apply((d) => addEntry(d), null);
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
            + {t("bibliographyEditor.add")}
          </button>
        </div>
      )}
    </Modal>
  );
};

BibliographyEditorModal.displayName = "BibliographyEditorModal";
