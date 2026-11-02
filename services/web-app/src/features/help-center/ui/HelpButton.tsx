import { useCallback } from "react";
import { clsx } from "clsx";
import { BookOpen } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useHelpStore } from "@entities/help";
import { useHelpHotkey } from "../lib/useHelpHotkey";

/**
 * Книжка в шапке: справка по текущему экрану, то же делает клавиша `?`. Есть на каждом экране:
 * экран без статьи всё равно открывает панель и говорит об этом, чтобы отсутствие справки было видно.
 */
export const HelpButton = () => {
  const { t } = useTranslation("help");
  const isOpen = useHelpStore((s) => s.isOpen);
  const toggle = useHelpStore((s) => s.toggle);
  const open = useHelpStore((s) => s.open);
  const openForScreen = useCallback(() => {
    open();
  }, [open]);
  useHelpHotkey(openForScreen);

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
          ? { width: 32, height: 32, color: "var(--accent)" }
          : { width: 32, height: 32 }
      }
    >
      <BookOpen size={16} />
    </button>
  );
};
