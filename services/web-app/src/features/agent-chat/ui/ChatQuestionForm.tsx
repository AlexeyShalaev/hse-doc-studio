import { useState } from "react";
import { Send } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { PendingQuestion } from "../lib/useAgentRunStream";

type ChatQuestionFormProps = {
  pending: PendingQuestion;
  submitting: boolean;
  onSubmit: (callId: string, answers: Record<string, string>) => void;
};

const OTHER = "__other__";

export const ChatQuestionForm = ({
  pending,
  submitting,
  onSubmit,
}: ChatQuestionFormProps) => {
  const { t } = useTranslation("agentChat");
  // Selected option labels per question index ("__other__" for the free-text
  // choice), plus the typed-in "Other" text per question.
  const [picked, setPicked] = useState<Record<number, string[]>>({});
  const [otherText, setOtherText] = useState<Record<number, string>>({});

  const toggle = (index: number, label: string, multi: boolean): void => {
    setPicked((prev) => {
      const current = prev[index] ?? [];
      if (!multi) return { ...prev, [index]: [label] };
      const next = current.includes(label)
        ? current.filter((item) => item !== label)
        : [...current, label];
      return { ...prev, [index]: next };
    });
  };

  const isAnswered = (index: number): boolean => {
    const sel = picked[index] ?? [];
    if (sel.length === 0) return false;
    if (sel.includes(OTHER) && !(otherText[index] ?? "").trim()) return false;
    return true;
  };

  const answerText = (index: number): string => {
    const sel = picked[index] ?? [];
    return sel
      .map((label) =>
        label === OTHER ? (otherText[index] ?? "").trim() : label,
      )
      .filter(Boolean)
      .join(", ");
  };

  const allAnswered = pending.questions.every((_, i) => isAnswered(i));

  const handleSubmit = (): void => {
    if (!allAnswered || submitting) return;
    const answers: Record<string, string> = {};
    pending.questions.forEach((q, i) => {
      answers[q.question] = answerText(i);
    });
    onSubmit(pending.callId, answers);
  };

  return (
    <div
      style={{
        flexShrink: 0,
        maxHeight: "20rem",
        overflowY: "auto",
        padding: "0.75rem",
        borderTop: "1px solid var(--border)",
        background: "var(--bg-1)",
        display: "flex",
        flexDirection: "column",
        gap: "0.875rem",
      }}
    >
      {pending.questions.map((q, i) => {
        const multi = q.multiSelect === true;
        const sel = picked[i] ?? [];
        return (
          <div key={i} className="flex flex-col" style={{ gap: "0.375rem" }}>
            <div className="flex items-center" style={{ gap: "0.375rem" }}>
              {q.header && (
                <span
                  className="mono"
                  style={{
                    fontSize: "0.59375rem",
                    textTransform: "uppercase",
                    letterSpacing: "0.025rem",
                    padding: "1px 0.375rem",
                    borderRadius: "62.4375rem",
                    background: "var(--bg-3)",
                    color: "var(--fg-2)",
                  }}
                >
                  {q.header}
                </span>
              )}
              {multi && (
                <span className="dim" style={{ fontSize: "0.625rem" }}>
                  {t("question.multiSelect")}
                </span>
              )}
            </div>
            <div style={{ fontSize: "0.78125rem", fontWeight: 500 }}>
              {q.question}
            </div>
            <div className="flex flex-col" style={{ gap: "0.25rem" }}>
              {q.options.map((opt) => (
                <Choice
                  key={opt.label}
                  label={opt.label}
                  description={opt.description}
                  checked={sel.includes(opt.label)}
                  multi={multi}
                  onClick={() => {
                    toggle(i, opt.label, multi);
                  }}
                />
              ))}
              <Choice
                label={t("question.other")}
                checked={sel.includes(OTHER)}
                multi={multi}
                onClick={() => {
                  toggle(i, OTHER, multi);
                }}
              />
              {sel.includes(OTHER) && (
                <input
                  type="text"
                  className="agent-composer-textarea mono"
                  autoFocus
                  value={otherText[i] ?? ""}
                  placeholder={t("question.otherPlaceholder")}
                  onChange={(e) => {
                    setOtherText((prev) => ({ ...prev, [i]: e.target.value }));
                  }}
                  style={{
                    marginLeft: "1.375rem",
                    padding: "0.25rem 0.5rem",
                    border: "1px solid var(--border)",
                    borderRadius: "0.375rem",
                    background: "var(--bg-0)",
                    fontSize: "0.75rem",
                  }}
                />
              )}
            </div>
          </div>
        );
      })}

      <button
        type="button"
        className="btn primary"
        disabled={!allAnswered || submitting}
        onClick={handleSubmit}
        style={{ alignSelf: "flex-end" }}
      >
        <Send size="0.75rem" />
        {t("question.submit")}
      </button>
    </div>
  );
};

type ChoiceProps = {
  label: string;
  description?: string | undefined;
  checked: boolean;
  multi: boolean;
  onClick: () => void;
};

const Choice = ({
  label,
  description,
  checked,
  multi,
  onClick,
}: ChoiceProps) => (
  <button
    type="button"
    className="flex items-start"
    onClick={onClick}
    style={{
      gap: "0.5rem",
      padding: "0.375rem 0.5rem",
      borderRadius: "0.375rem",
      textAlign: "left",
      border: "1px solid",
      borderColor: checked ? "var(--accent)" : "var(--border)",
      background: checked ? "var(--accent-soft, var(--bg-2))" : "transparent",
      cursor: "pointer",
    }}
  >
    <span
      style={{
        flexShrink: 0,
        width: "0.875rem",
        height: "0.875rem",
        marginTop: 1,
        borderRadius: multi ? "0.1875rem" : "62.4375rem",
        border: "1.5px solid",
        borderColor: checked ? "var(--accent)" : "var(--fg-3)",
        background: checked ? "var(--accent)" : "transparent",
      }}
    />
    <span style={{ minWidth: 0 }}>
      <span style={{ fontSize: "0.78125rem" }}>{label}</span>
      {description && (
        <span
          className="dim"
          style={{ display: "block", fontSize: "0.6875rem" }}
        >
          {description}
        </span>
      )}
    </span>
  </button>
);
