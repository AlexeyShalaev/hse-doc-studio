import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Check } from "lucide-react";
import type { OnboardingAnswers } from "@entities/onboarding";
import { usePacks } from "@entities/template-catalog";
import { questionsFor } from "../../lib/questions";
import { workOptions } from "../../lib/templateSuggestion";

type Option = { value: string; label: string };

export type QuestionnaireProps = {
  initial: OnboardingAnswers;
  onDone: (answers: OnboardingAnswers, next: "tour" | "demo") => void;
  onSkipAll: () => void;
};

/** Короткая анкета: шаг за шагом, любой вопрос можно пропустить. */
export const Questionnaire = ({
  initial,
  onDone,
  onSkipAll,
}: QuestionnaireProps) => {
  const { t, i18n } = useTranslation("onboarding");
  const [answers, setAnswers] = useState<OnboardingAnswers>(initial);
  const [index, setIndex] = useState(-1);
  const packs = usePacks();
  const questions = questionsFor(answers);
  const id = questions[index];

  const options = useMemo((): Option[] => {
    const skills = (q: "latex" | "git") =>
      (["none", "some", "pro"] as const).map((v) => ({
        value: v,
        label: t(`questions.${q}.${v}`),
      }));
    switch (id) {
      case "role":
        return (["student", "supervisor", "admin"] as const).map((v) => ({
          value: v,
          label: t(`questions.role.${v}`),
        }));
      case "work":
        return [
          ...workOptions(packs.data ?? [], i18n.language),
          { value: "other", label: t("questions.work.other") },
        ];
      case "latex":
        return skills("latex");
      case "git":
        return skills("git");
      default:
        return [];
    }
  }, [id, packs.data, i18n.language, t]);

  const advance = (next: OnboardingAnswers) => {
    const list = questionsFor(next);
    const at = id ? list.indexOf(id) : -1;
    if (at + 1 >= list.length) {
      onDone(next, "tour");
      return;
    }
    setIndex(at + 1);
  };

  if (index === -1) {
    return (
      <div className="flex flex-col" style={{ gap: 14 }}>
        <span
          className="mono dim"
          style={{ fontSize: 10.5, letterSpacing: "0.08em" }}
        >
          {t("intro.kicker")}
        </span>
        <h2 style={{ margin: 0, fontSize: 20, fontWeight: 600 }}>
          {t("intro.title")}
        </h2>
        <p style={{ margin: 0, fontSize: 13.5, lineHeight: 1.55 }}>
          {t("intro.body")}
        </p>
        <p className="dim" style={{ margin: 0, fontSize: 13 }}>
          {t("intro.plan")}
        </p>
        <div
          className="flex items-center justify-between"
          style={{ gap: 8, flexWrap: "wrap", marginTop: 6 }}
        >
          <button
            type="button"
            className="btn ghost"
            onClick={onSkipAll}
            data-testid="onboarding-skip"
          >
            {t("intro.skip")}
          </button>
          <button
            type="button"
            className="btn primary"
            autoFocus
            onClick={() => {
              setIndex(0);
            }}
            data-testid="onboarding-start"
          >
            {t("intro.start")}
          </button>
        </div>
      </div>
    );
  }

  const title =
    id === "work" && answers.role === "supervisor"
      ? t("questions.work.titleSupervisor")
      : t(`questions.${id ?? "role"}.title`);

  return (
    <div className="flex flex-col" style={{ gap: 14 }}>
      <span
        className="mono dim"
        aria-live="polite"
        style={{ fontSize: 10.5, letterSpacing: "0.08em" }}
      >
        {t("intro.progress", { current: index + 1, total: questions.length })}
      </span>
      <h2
        id="onboarding-question"
        style={{ margin: 0, fontSize: 18, fontWeight: 600 }}
      >
        {title}
      </h2>
      <div
        role="radiogroup"
        aria-labelledby="onboarding-question"
        className="flex flex-col"
        style={{ gap: 6, maxHeight: 300, overflowY: "auto" }}
      >
        {id === "work" && packs.isLoading && (
          <span className="dim" style={{ fontSize: 12.5 }}>
            {t("questions.work.loading")}
          </span>
        )}
        {options.map((option, i) => {
          const selected = id !== undefined && answers[id] === option.value;
          return (
            <button
              key={option.value}
              type="button"
              role="radio"
              aria-checked={selected}
              autoFocus={i === 0}
              data-testid={`onboarding-answer-${id ?? ""}-${option.value}`}
              className="card hover flex items-center justify-between"
              style={{
                padding: "10px 12px",
                textAlign: "left",
                fontSize: 13.5,
                borderColor: selected ? "var(--accent)" : undefined,
              }}
              onClick={() => {
                if (!id) return;
                const next = { ...answers, [id]: option.value };
                setAnswers(next);
                advance(next);
              }}
            >
              <span>{option.label}</span>
              {selected && (
                <Check size={14} style={{ color: "var(--accent)" }} />
              )}
            </button>
          );
        })}
      </div>
      <div
        className="flex items-center justify-between"
        style={{ gap: 8, flexWrap: "wrap" }}
      >
        <button
          type="button"
          className="btn ghost sm"
          onClick={() => {
            setIndex(index - 1);
          }}
        >
          {t("intro.back")}
        </button>
        <div className="flex items-center" style={{ gap: 6 }}>
          <button
            type="button"
            className="btn ghost sm"
            onClick={() => {
              onDone(answers, "demo");
            }}
            data-testid="onboarding-demo-only"
          >
            {t("intro.demoOnly")}
          </button>
          <button
            type="button"
            className="btn sm"
            onClick={() => {
              advance(answers);
            }}
            data-testid="onboarding-skip-question"
          >
            {t("intro.skipQuestion")}
          </button>
        </div>
      </div>
    </div>
  );
};
