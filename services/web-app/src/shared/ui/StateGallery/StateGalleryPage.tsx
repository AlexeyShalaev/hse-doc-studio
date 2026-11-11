import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { useThemeStore, type Theme } from "@shared/lib";
import { useIsPhoneWidth } from "@shared/lib/viewport";
import type { GalleryEntry, GallerySection } from "@shared/lib/stateGallery";
import { GalleryEntryCard, type GalleryDemo } from "./GalleryEntryCard";

const THEMES: { value: Theme; label: string }[] = [
  { value: "system", label: "Системная" },
  { value: "dark", label: "Тёмная" },
  { value: "light", label: "Светлая" },
  { value: "blueprint", label: "Чертёж" },
];

export type StateGalleryPageProps = {
  /** Заголовок страницы. */
  title: string;
  /** Адрес страницы: от него строятся ссылки на разделы. */
  basePath: string;
  /** Метка для проверки сборки: в рабочий бандл попасть не должна. */
  marker: string;
  /** Демо-API: нужен живым записям. Без него они только описаны. */
  demo?: GalleryDemo | null;
  /** Разделы для показа. */
  sections: GallerySection[];
};

const Segmented = <T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: { value: T; label: string }[];
  onChange: (value: T) => void;
}) => (
  <div
    role="group"
    aria-label={label}
    className="flex items-center"
    style={{
      gap: "0.125rem",
      padding: "0.125rem",
      borderRadius: "0.5rem",
      border: "1px solid var(--border)",
      background: "var(--bg-1)",
    }}
  >
    {options.map((option) => (
      <button
        key={option.value}
        type="button"
        className="btn sm"
        aria-pressed={option.value === value}
        onClick={() => {
          onChange(option.value);
        }}
        style={{
          border: "none",
          background: option.value === value ? "var(--bg-3)" : "transparent",
          fontWeight: option.value === value ? 600 : 400,
        }}
      >
        {option.label}
      </button>
    ))}
  </div>
);

/**
 * Общий каркас галереи состояний (только в разработке): разделы и группы
 * записей на готовых данных, переключение темы и языка. Живые записи ходят в
 * демо-API, остальные не обращаются к серверу. Страницы-оболочки задают заголовок,
 * адрес и набор разделов.
 */
export const StateGalleryPage = ({
  title,
  basePath,
  marker,
  demo = null,
  sections,
}: StateGalleryPageProps) => {
  const theme = useThemeStore((state) => state.theme);
  const setTheme = useThemeStore((state) => state.setTheme);
  const lang = useThemeStore((state) => state.lang);
  const setLang = useThemeStore((state) => state.setLang);
  const [active, setActive] = useState<{ id: string; run: number } | null>(
    null,
  );
  const runs = useRef(0);
  // Раскладка по брейкпоинту телефона из viewport: адаптивных вариантов Tailwind (sm:,
  // max-sm:) в сборке нет, с ними навигация на любом окне ложилась над содержимым.
  const isPhone = useIsPhoneWidth();
  // ?section=conflicts оставляет один раздел: удобно показать его целиком.
  const [searchParams] = useSearchParams();
  const only = searchParams.get("section");
  const visible = sections.some((section) => section.id === only)
    ? sections.filter((section) => section.id === only)
    : sections;

  // Живая запись ставит демо-мир в свой сценарий и собирается заново.
  const openLive = useCallback(
    (entry: GalleryEntry): void => {
      if (!demo || entry.scenario === undefined) return;
      demo.activate(entry.scenario);
      runs.current += 1;
      setActive({ id: entry.id, run: runs.current });
    },
    [demo],
  );

  // ?open=live_conflicts открывает живую запись сразу: ссылкой можно поделиться.
  const openId = searchParams.get("open");
  useEffect(() => {
    if (openId === null) return;
    const entry = sections
      .flatMap((section) => section.groups)
      .flatMap((group) => group.entries)
      .find((item) => item.id === openId);
    if (entry?.scenario === undefined) return;
    openLive(entry);
    requestAnimationFrame(() => {
      document
        .getElementById(`entry-${entry.id}`)
        ?.scrollIntoView({ block: "start" });
    });
  }, [openId, sections, openLive]);

  const total = sections.reduce(
    (sum, section) =>
      sum +
      section.groups.reduce((inner, group) => inner + group.entries.length, 0),
    0,
  );

  return (
    <div
      className="flex flex-col"
      data-dev-gallery={marker}
      style={{ flex: 1, minHeight: 0, background: "var(--bg-0)" }}
    >
      <header
        className="flex items-center flex-wrap"
        style={{
          gap: "1rem",
          padding: "0.625rem 1.25rem",
          borderBottom: "1px solid var(--border)",
          background: "var(--bg-1)",
        }}
      >
        <div style={{ flex: 1, minWidth: "13.75rem" }}>
          <h1 style={{ margin: 0, fontSize: "0.9375rem", fontWeight: 600 }}>
            {title}
          </h1>
          <p
            className="dim"
            style={{ margin: "0.125rem 0 0", fontSize: "0.75rem" }}
          >
            {total} состояний. Страница есть только в разработке.
          </p>
        </div>
        <Segmented
          label="Язык"
          value={lang}
          options={[
            { value: "ru", label: "RU" },
            { value: "en", label: "EN" },
          ]}
          onChange={setLang}
        />
        <Segmented
          label="Тема"
          value={theme}
          options={THEMES}
          onChange={setTheme}
        />
        <Link to="/" className="btn sm" style={{ textDecoration: "none" }}>
          К приложению
        </Link>
      </header>

      <div
        className="flex"
        style={{
          flex: 1,
          minHeight: 0,
          flexDirection: isPhone ? "column" : "row",
        }}
      >
        {/* На телефоне навигация ложится над содержимым и не отнимает ширину */}
        <nav
          aria-label="Разделы галереи"
          className="flex flex-col"
          data-testid="gallery-nav"
          style={{
            flexShrink: 0,
            overflowY: "auto",
            padding: "0.875rem 0.625rem",
            gap: "0.875rem",
            background: "var(--bg-1)",
            ...(isPhone
              ? {
                  width: "100%",
                  maxHeight: "10rem",
                  borderBottom: "1px solid var(--border)",
                }
              : { width: "15.625rem", borderRight: "1px solid var(--border)" }),
          }}
        >
          <Link
            to={basePath}
            aria-current={
              visible.length === sections.length ? "page" : undefined
            }
            style={{
              padding: "0.125rem 0.5rem",
              fontSize: "0.75rem",
              textDecoration: "none",
              color: "var(--fg-2)",
            }}
          >
            Все разделы
          </Link>
          {sections.map((section) => (
            <div key={section.id}>
              <Link
                to={`${basePath}?section=${section.id}`}
                style={{
                  display: "block",
                  padding: "0.125rem 0.5rem",
                  fontSize: "0.78125rem",
                  fontWeight: 600,
                  color: "var(--fg-0)",
                  textDecoration: "none",
                }}
              >
                {section.title}
              </Link>
              {visible.includes(section) &&
                section.groups.map((group) => (
                  <a
                    key={group.id}
                    href={`#group-${group.id}`}
                    className="dim"
                    style={{
                      display: "block",
                      padding: "0.125rem 0.5rem 0.125rem 1.125rem",
                      fontSize: "0.75rem",
                      textDecoration: "none",
                    }}
                  >
                    {group.title}
                  </a>
                ))}
            </div>
          ))}
        </nav>

        <main
          data-gallery-scroll
          style={{
            flex: 1,
            minWidth: 0,
            minHeight: 0,
            overflowY: "auto",
            padding: isPhone ? "1.25rem 0.75rem 5rem" : "1.25rem 1.75rem 5rem",
          }}
        >
          {visible.map((section) => (
            <div key={section.id} style={{ marginBottom: "3.5rem" }}>
              <h2
                id={`section-${section.id}`}
                style={{
                  margin: "0 0 1.125rem",
                  fontSize: "1.25rem",
                  fontWeight: 650,
                  scrollMarginTop: 16,
                }}
              >
                {section.title}
              </h2>
              {section.groups.map((group) => (
                <div key={group.id} style={{ marginBottom: "2.25rem" }}>
                  <h3
                    id={`group-${group.id}`}
                    style={{
                      margin: "0 0 0.25rem",
                      fontSize: "0.8125rem",
                      fontWeight: 600,
                      letterSpacing: "0.04em",
                      textTransform: "uppercase",
                      color: "var(--fg-2)",
                      scrollMarginTop: 16,
                    }}
                  >
                    {group.title}
                  </h3>
                  {group.description && (
                    <p
                      className="dim"
                      style={{ margin: "0 0 0.875rem", fontSize: "0.78125rem" }}
                    >
                      {group.description}
                    </p>
                  )}
                  <div
                    className="flex flex-col"
                    style={{ gap: "1.75rem", marginTop: "0.875rem" }}
                  >
                    {group.entries.map((entry) => (
                      <GalleryEntryCard
                        key={entry.id}
                        entry={entry}
                        demo={demo}
                        activeRun={active?.id === entry.id ? active.run : null}
                        onOpenLive={openLive}
                        onCloseLive={() => {
                          setActive(null);
                        }}
                      />
                    ))}
                  </div>
                </div>
              ))}
            </div>
          ))}
        </main>
      </div>
    </div>
  );
};
