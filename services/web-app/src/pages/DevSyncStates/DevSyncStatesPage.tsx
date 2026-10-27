import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { useThemeStore, type Theme } from "@shared/lib";
import type { GalleryEntry, GallerySection } from "@shared/lib/stateGallery";
import { GalleryEntryCard, type GalleryDemo } from "./GalleryEntryCard";
import { buildGallerySections } from "./gallerySections";

// Метка для проверки сборки: в рабочий бандл этой строки попасть не должно.
export const DEV_SYNC_STATES_MARKER = "hse-dev-sync-states-gallery";

const THEMES: { value: Theme; label: string }[] = [
  { value: "system", label: "Системная" },
  { value: "dark", label: "Тёмная" },
  { value: "light", label: "Светлая" },
  { value: "blueprint", label: "Чертёж" },
];

export type DevSyncStatesPageProps = {
  /** Демо-API: нужен живым записям. Без него они только описаны. */
  demo?: GalleryDemo | null;
  /** Разделы для проверки; по умолчанию собираются из всех фич. */
  sections?: GallerySection[];
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
      gap: 2,
      padding: 2,
      borderRadius: 8,
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
 * Галерея состояний git-синхронизации (только в разработке, адрес
 * /dev/sync-states): каждое состояние кнопки, панелей, шагов подключения,
 * клонирования, конфликтов и обмена файлом на готовых данных, с переключением
 * темы и языка. Живые записи ходят в демо-API, остальные не обращаются к серверу.
 */
export const DevSyncStatesPage = ({
  demo = null,
  sections: sectionsProp,
}: DevSyncStatesPageProps) => {
  const sections = useMemo(
    () => sectionsProp ?? buildGallerySections(),
    [sectionsProp],
  );
  const theme = useThemeStore((state) => state.theme);
  const setTheme = useThemeStore((state) => state.setTheme);
  const lang = useThemeStore((state) => state.lang);
  const setLang = useThemeStore((state) => state.setLang);
  const [active, setActive] = useState<{ id: string; run: number } | null>(
    null,
  );
  const runs = useRef(0);
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
      data-dev-gallery={DEV_SYNC_STATES_MARKER}
      style={{ flex: 1, minHeight: 0, background: "var(--bg-0)" }}
    >
      <header
        className="flex items-center flex-wrap"
        style={{
          gap: 16,
          padding: "10px 20px",
          borderBottom: "1px solid var(--border)",
          background: "var(--bg-1)",
        }}
      >
        <div style={{ flex: 1, minWidth: 220 }}>
          <h1 style={{ margin: 0, fontSize: 15, fontWeight: 600 }}>
            Состояния синхронизации
          </h1>
          <p className="dim" style={{ margin: "2px 0 0", fontSize: 12 }}>
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

      <div className="flex" style={{ flex: 1, minHeight: 0 }}>
        <nav
          aria-label="Разделы галереи"
          className="flex flex-col"
          style={{
            width: 250,
            flexShrink: 0,
            overflowY: "auto",
            padding: "14px 10px",
            gap: 14,
            borderRight: "1px solid var(--border)",
            background: "var(--bg-1)",
          }}
        >
          <Link
            to="/dev/sync-states"
            aria-current={
              visible.length === sections.length ? "page" : undefined
            }
            style={{
              padding: "2px 8px",
              fontSize: 12,
              textDecoration: "none",
              color: "var(--fg-2)",
            }}
          >
            Все разделы
          </Link>
          {sections.map((section) => (
            <div key={section.id}>
              <Link
                to={`/dev/sync-states?section=${section.id}`}
                style={{
                  display: "block",
                  padding: "2px 8px",
                  fontSize: 12.5,
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
                      padding: "2px 8px 2px 18px",
                      fontSize: 12,
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
            overflowY: "auto",
            padding: "20px 28px 80px",
          }}
        >
          {visible.map((section) => (
            <div key={section.id} style={{ marginBottom: 56 }}>
              <h2
                id={`section-${section.id}`}
                style={{
                  margin: "0 0 18px",
                  fontSize: 20,
                  fontWeight: 650,
                  scrollMarginTop: 16,
                }}
              >
                {section.title}
              </h2>
              {section.groups.map((group) => (
                <div key={group.id} style={{ marginBottom: 36 }}>
                  <h3
                    id={`group-${group.id}`}
                    style={{
                      margin: "0 0 4px",
                      fontSize: 13,
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
                      style={{ margin: "0 0 14px", fontSize: 12.5 }}
                    >
                      {group.description}
                    </p>
                  )}
                  <div
                    className="flex flex-col"
                    style={{ gap: 28, marginTop: 14 }}
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
