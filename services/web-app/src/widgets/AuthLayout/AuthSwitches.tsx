import { clsx } from "clsx";
import { Moon, Sun } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useThemeStore } from "@shared/lib";
import { PREFERS_DARK_QUERY, resolveTheme } from "@shared/lib/theme";
import type { Lang } from "@shared/api";

const LANGUAGES: readonly { id: Lang; label: string }[] = [
  { id: "ru", label: "RU" },
  { id: "en", label: "EN" },
];

/** Язык и тема на экранах без сессии: настроек аккаунта там ещё нет. */
export const AuthSwitches = () => {
  const { t } = useTranslation("auth");
  const lang = useThemeStore((s) => s.lang);
  const setLang = useThemeStore((s) => s.setLang);
  const theme = useThemeStore((s) => s.theme);
  const setTheme = useThemeStore((s) => s.setTheme);
  const prefersDark =
    typeof window.matchMedia === "function" &&
    window.matchMedia(PREFERS_DARK_QUERY).matches;
  const dark = resolveTheme(theme, prefersDark) !== "light";

  return (
    <div className="flex items-center" style={{ gap: 8 }}>
      <div className="seg" role="group" aria-label={t("layout.language")}>
        {LANGUAGES.map((item) => (
          <button
            key={item.id}
            type="button"
            className={clsx(lang === item.id && "active")}
            aria-pressed={lang === item.id}
            onClick={() => {
              setLang(item.id);
            }}
          >
            {item.label}
          </button>
        ))}
      </div>
      <button
        type="button"
        className="btn sm"
        data-testid="auth-theme-toggle"
        aria-label={t(dark ? "layout.themeLight" : "layout.themeDark")}
        title={t(dark ? "layout.themeLight" : "layout.themeDark")}
        onClick={() => {
          setTheme(dark ? "light" : "dark");
        }}
      >
        {dark ? <Sun size={14} aria-hidden /> : <Moon size={14} aria-hidden />}
      </button>
    </div>
  );
};
