import { clsx } from "clsx";
import { BookOpen } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useHelpStore } from "@entities/help";

/**
 * Книжка в шапке для тех, у кого нет меню «Справка» (гость по ссылке): справка по текущему экрану.
 * Вошедшие открывают её из меню «Справка» (features/onboarding) или клавишей `?` (HelpHost).
 */
export const HelpButton = () => {
  const { t } = useTranslation("help");
  const isOpen = useHelpStore((s) => s.isOpen);
  const toggle = useHelpStore((s) => s.toggle);

  return (
    <button
      type="button"
      className={clsx("icon-btn tt", isOpen && "active")}
      data-tt={t("button")}
      aria-label={t("button")}
      aria-expanded={isOpen}
      data-testid="help-button"
      onClick={toggle}
      style={
        isOpen
          ? { width: "2rem", height: "2rem", color: "var(--accent)" }
          : { width: "2rem", height: "2rem" }
      }
    >
      <BookOpen size="1rem" />
    </button>
  );
};
