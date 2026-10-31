import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useDebouncedValue } from "@shared/lib";
import { useMentionCandidates, type MentionCandidate } from "@entities/review";
import {
  insertMention,
  mentionQueryAt,
  mentionsInText,
  type PickedMention,
} from "../lib/mentions";

export type CommentComposerProps = {
  projectId: string;
  placeholder: string;
  submitLabel: string;
  initialText?: string;
  busy?: boolean;
  error?: string | null;
  autoFocus?: boolean;
  onSubmit: (body: string, mentions: string[]) => void;
  onCancel?: () => void;
};

/** Поле комментария с подсказкой людей проекта по `@` и отправкой по Ctrl/Cmd+Enter. */
export const CommentComposer = ({
  projectId,
  placeholder,
  submitLabel,
  initialText = "",
  busy = false,
  error = null,
  autoFocus = false,
  onSubmit,
  onCancel,
}: CommentComposerProps) => {
  const { t } = useTranslation("review");
  const [text, setText] = useState(initialText);
  const [caret, setCaret] = useState(initialText.length);
  const [picked, setPicked] = useState<PickedMention[]>([]);
  const [active, setActive] = useState(0);
  const area = useRef<HTMLTextAreaElement>(null);
  const at = mentionQueryAt(text, caret);
  const query = useDebouncedValue(at?.query ?? "", 150);
  const { data: candidates = [], isFetched } = useMentionCandidates(
    projectId,
    query,
    at !== null,
  );

  useEffect(() => {
    if (autoFocus) area.current?.focus();
  }, [autoFocus]);

  const choose = (candidate: MentionCandidate): void => {
    if (!at) return;
    const next = insertMention(text, at, candidate.name);
    setText(next.text);
    setPicked((list) => [
      ...list,
      { userId: candidate.user_id, name: candidate.name },
    ]);
    setActive(0);
    requestAnimationFrame(() => {
      area.current?.focus();
      area.current?.setSelectionRange(next.caret, next.caret);
      setCaret(next.caret);
    });
  };

  const submit = (): void => {
    const body = text.trim();
    if (body === "" || busy) return;
    onSubmit(body, mentionsInText(body, picked));
  };

  const showList = at !== null && isFetched;
  return (
    <div className="flex flex-col" style={{ gap: 6, position: "relative" }}>
      <textarea
        ref={area}
        value={text}
        rows={3}
        placeholder={placeholder}
        aria-label={placeholder}
        data-testid="review-composer"
        className="input"
        style={{ resize: "vertical", fontSize: 12.5 }}
        onChange={(event) => {
          setText(event.target.value);
          setCaret(event.target.selectionStart);
          setActive(0);
        }}
        onSelect={(event) => {
          setCaret(event.currentTarget.selectionStart);
        }}
        onKeyDown={(event) => {
          if (showList && candidates.length > 0) {
            if (event.key === "ArrowDown" || event.key === "ArrowUp") {
              event.preventDefault();
              const step = event.key === "ArrowDown" ? 1 : -1;
              setActive(
                (i) => (i + step + candidates.length) % candidates.length,
              );
              return;
            }
            if (event.key === "Enter" || event.key === "Tab") {
              event.preventDefault();
              const chosen = candidates[active];
              if (chosen) choose(chosen);
              return;
            }
          }
          if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
            event.preventDefault();
            submit();
          } else if (event.key === "Escape" && onCancel) {
            event.preventDefault();
            onCancel();
          }
        }}
      />
      {showList && (
        <ul
          role="listbox"
          data-testid="review-mention-list"
          style={{
            position: "absolute",
            left: 0,
            right: 0,
            bottom: "100%",
            margin: 0,
            padding: 4,
            listStyle: "none",
            background: "var(--bg-1)",
            border: "1px solid var(--border)",
            borderRadius: "var(--r-2)",
            boxShadow: "var(--shadow-2)",
            zIndex: 5,
          }}
        >
          {candidates.length === 0 && (
            <li className="dim" style={{ padding: "4px 8px", fontSize: 12 }}>
              {t("mentionNone")}
            </li>
          )}
          {candidates.map((candidate, index) => (
            <li
              key={candidate.user_id}
              role="option"
              aria-selected={index === active}
              style={{
                padding: "4px 8px",
                fontSize: 12.5,
                cursor: "pointer",
                borderRadius: "var(--r-1)",
                background: index === active ? "var(--bg-3)" : "transparent",
              }}
              onMouseDown={(event) => {
                event.preventDefault();
                choose(candidate);
              }}
            >
              {candidate.name}
              {candidate.detail && (
                <span className="dim" style={{ marginLeft: 6, fontSize: 11 }}>
                  {candidate.detail}
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
      {error && (
        <span role="alert" style={{ color: "var(--c-err)", fontSize: 11.5 }}>
          {error}
        </span>
      )}
      <div className="flex" style={{ gap: 6, justifyContent: "flex-end" }}>
        {onCancel && (
          <button type="button" className="btn xs ghost" onClick={onCancel}>
            {t("cancel")}
          </button>
        )}
        <button
          type="button"
          className="btn xs primary"
          disabled={busy || text.trim() === ""}
          data-testid="review-composer-submit"
          onClick={submit}
        >
          {submitLabel}
        </button>
      </div>
    </div>
  );
};
