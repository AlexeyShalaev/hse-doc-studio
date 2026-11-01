import { clsx } from "clsx";
import { Check } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@shared/ui";
import type { Lang } from "@shared/api";
import { StepActions, StepHeading } from "./parts";

const LANGUAGES: readonly { id: Lang; name: string; native: string }[] = [
  { id: "ru", name: "Русский", native: "RU" },
  { id: "en", name: "English", native: "EN" },
];

export type LanguageStepProps = {
  lang: Lang;
  onLang: (lang: Lang) => void;
  onNext: () => void;
};

/** Шаг 1: язык мастера. Дальше каждый человек выбирает свой язык в аккаунте. */
export const LanguageStep = ({ lang, onLang, onNext }: LanguageStepProps) => {
  const { t } = useTranslation("auth");
  return (
    <section data-testid="setup-step-language" aria-labelledby="setup-title">
      <StepHeading
        id="setup-title"
        title={t("setup.language.title")}
        lead={t("setup.language.lead")}
      />
      <div
        role="radiogroup"
        aria-label={t("setup.language.title")}
        className="flex flex-col"
        style={{ gap: 8 }}
      >
        {LANGUAGES.map((item) => {
          const active = lang === item.id;
          return (
            <button
              key={item.id}
              type="button"
              role="radio"
              aria-checked={active}
              data-testid={`setup-lang-${item.id}`}
              onClick={() => {
                onLang(item.id);
              }}
              className={clsx("flex items-center text-left")}
              style={{
                gap: 12,
                padding: "10px 14px",
                borderRadius: "var(--r-3)",
                border: `1px solid ${active ? "var(--accent)" : "var(--border)"}`,
                background: active ? "var(--accent-soft)" : "var(--bg-1)",
                color: "var(--fg-0)",
                cursor: "pointer",
              }}
            >
              <span
                className="mono"
                style={{ fontSize: 12, color: "var(--fg-2)", width: 22 }}
              >
                {item.native}
              </span>
              <span style={{ flex: 1, fontSize: 14, fontWeight: 500 }}>
                {item.name}
              </span>
              {active && (
                <Check
                  size={16}
                  aria-hidden
                  style={{ color: "var(--accent)" }}
                />
              )}
            </button>
          );
        })}
      </div>
      <p style={{ margin: "12px 0 0", fontSize: 12.5, color: "var(--fg-2)" }}>
        {t("setup.language.note")}
      </p>
      <StepActions
        primary={
          <Button type="button" onClick={onNext} data-testid="setup-next">
            {t("setup.next")}
          </Button>
        }
      />
    </section>
  );
};
