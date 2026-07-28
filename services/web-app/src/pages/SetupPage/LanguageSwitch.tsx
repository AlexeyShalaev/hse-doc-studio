import { clsx } from "clsx";
import { useThemeStore } from "@shared/lib";
import type { Lang } from "@shared/api";

const LANGUAGES: readonly { id: Lang; label: string }[] = [
  { id: "ru", label: "RU" },
  { id: "en", label: "EN" },
];

/**
 * Выбор языка на экране первоначальной настройки.
 *
 * Язык при первом запуске определяется по локали браузера (загрузочный скрипт в
 * index.html), и обычно угадывает верно. Но промах вполне возможен — русский
 * студент за англоязычной Windows, — а настройки приложения до окончания
 * установки недоступны, и человек застрял бы в чужом языке на весь мастер.
 *
 * В отличие от настроек внешнего вида, выбор НЕ дублируется в настройки
 * бэкенда: каталог данных ещё не подключён, и запись ушла бы внутрь контейнера,
 * то есть пропала бы при первом же пересоздании. Локального хранилища браузера
 * здесь достаточно — оно переживает пересоздание, в отличие от контейнера.
 */
export const LanguageSwitch = () => {
  const lang = useThemeStore((state) => state.lang);
  const setLang = useThemeStore((state) => state.setLang);

  return (
    <div className="seg" style={{ flexShrink: 0 }}>
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
  );
};
