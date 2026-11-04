import { clsx } from "clsx";
import { useTranslation } from "react-i18next";
import { useThemeStore, type Theme } from "@shared/lib";
import type { Lang } from "@shared/api";

const THEMES: readonly { id: Theme; key: string }[] = [
  { id: "system", key: "accountMenu.themeSystem" },
  { id: "dark", key: "accountMenu.themeDark" },
  { id: "light", key: "accountMenu.themeLight" },
];

const LANGUAGES: readonly { id: Lang; label: string }[] = [
  { id: "ru", label: "RU" },
  { id: "en", label: "EN" },
];

/**
 * Тема и язык в меню аккаунта. На десктопе они в «Настройках», и титлбар их не показывает; на
 * телефоне настройки далеко, а язык и тему меняют чаще всего сразу при входе.
 */
export const QuickAppearance = () => {
  const { t } = useTranslation("appChrome");
  const theme = useThemeStore((s) => s.theme);
  const setTheme = useThemeStore((s) => s.setTheme);
  const lang = useThemeStore((s) => s.lang);
  const setLang = useThemeStore((s) => s.setLang);
  return (
    <div
      className="quick-appearance"
      role="group"
      aria-label={t("accountMenu.appearance")}
      data-testid="account-menu-appearance"
    >
      <div
        className="seg seg-fill"
        role="group"
        aria-label={t("accountMenu.theme")}
      >
        {THEMES.map((item) => (
          <button
            key={item.id}
            type="button"
            className={clsx(theme === item.id && "active")}
            aria-pressed={theme === item.id}
            data-testid={`account-menu-theme-${item.id}`}
            onClick={() => {
              setTheme(item.id);
            }}
          >
            {t(item.key)}
          </button>
        ))}
      </div>
      <div
        className="seg seg-fill"
        role="group"
        aria-label={t("accountMenu.language")}
      >
        {LANGUAGES.map((item) => (
          <button
            key={item.id}
            type="button"
            className={clsx(lang === item.id && "active")}
            aria-pressed={lang === item.id}
            data-testid={`account-menu-lang-${item.id}`}
            onClick={() => {
              setLang(item.id);
            }}
          >
            {item.label}
          </button>
        ))}
      </div>
    </div>
  );
};
