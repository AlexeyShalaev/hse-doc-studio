import { useEffect, useMemo, useRef, useState } from "react";
import { clsx } from "clsx";
import { ArrowLeft, BookOpen, ExternalLink, Search, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  helpApi,
  useHelpArticle,
  useHelpMap,
  useHelpStore,
  type HelpArticle,
} from "@entities/help";
import { useThemeStore } from "@shared/lib";
import { Spinner } from "@shared/ui";
import { renderInline } from "../lib/inlineMarkdown";
import { useCurrentHelpKeys } from "../lib/useCurrentHelp";

/** Кадры сняты в светлой и тёмной теме; «blueprint» Студии ближе к тёмной, «system» как у ОС. */
const useShotTheme = (): "light" | "dark" => {
  const theme = useThemeStore((s) => s.theme);
  if (theme === "light") return "light";
  if (theme === "system") {
    return window.matchMedia("(prefers-color-scheme: dark)").matches
      ? "dark"
      : "light";
  }
  return "dark";
};

const ArticleBody = ({
  article,
  focusStep,
}: {
  article: HelpArticle;
  focusStep?: number | undefined;
}) => {
  const { t } = useTranslation("help");
  const theme = useShotTheme();
  const focused = useRef<HTMLLIElement | null>(null);

  // Открыто значком у поля: прокрутить к его шагу. `center`, чтобы предыдущий шаг (контекст) остался виден.
  useEffect(() => {
    if (!focusStep) return;
    focused.current?.scrollIntoView?.({ block: "center", behavior: "smooth" });
  }, [focusStep, article.key]);

  const video = article.video?.[theme];
  return (
    <>
      {video && (
        <video
          key={`${article.key}-${theme}`}
          className="help-panel-video"
          controls
          muted
          playsInline
          preload="none"
          poster={video.poster}
          data-testid="help-video"
        >
          <source src={video.mp4} type="video/mp4" />
        </video>
      )}
      <ol className="help-panel-steps">
        {article.steps.map((step, index) => {
          const isFocused = focusStep === index + 1;
          const shot = step.shot?.[theme];
          return (
            <li
              key={`${article.key}-${String(index)}`}
              ref={isFocused ? focused : undefined}
              className={clsx(isFocused && "is-focused")}
              data-testid={`help-step-${String(index + 1)}`}
            >
              <span className="help-panel-step-no" aria-hidden="true">
                {index + 1}
              </span>
              <div className="help-panel-step-body">
                <p>{renderInline(step.text)}</p>
                {step.hint && (
                  <p className="help-panel-hint">{renderInline(step.hint)}</p>
                )}
                {shot && (
                  <img
                    src={shot}
                    alt={t("stepShot", { n: index + 1 })}
                    loading="lazy"
                    decoding="async"
                    onError={(event) => {
                      // Кадр ещё не снят: шаг остаётся текстом, без битой картинки.
                      event.currentTarget.style.display = "none";
                    }}
                  />
                )}
              </div>
            </li>
          );
        })}
      </ol>
      {article.verified && (
        <p className="help-panel-verified">
          {t("verified", {
            date: article.verified.at,
            version: article.verified.appVersion,
          })}
        </p>
      )}
    </>
  );
};

/**
 * Панель справки поверх экрана, справа. Рисует статью из её ДАННЫХ (те же шаги, что на сайте),
 * в теме и шрифтах приложения. Экран без статьи всё равно открывает панель и говорит об этом,
 * со ссылкой на всю справку и поиском по каталогу.
 */
export const HelpPanel = () => {
  const { t } = useTranslation("help");
  const lang = useThemeStore((s) => s.lang);
  const { isOpen, articleKey, focusStep, close, open } = useHelpStore();
  const [query, setQuery] = useState("");
  const routeKeys = useCurrentHelpKeys(isOpen);
  const { data: map, isError: mapError } = useHelpMap(lang, isOpen);
  const resolvedKey = articleKey ?? routeKeys[0];
  const {
    data: article,
    isLoading,
    isError,
  } = useHelpArticle(lang, resolvedKey, isOpen);

  useEffect(() => {
    if (!isOpen) return undefined;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") close();
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
    };
  }, [isOpen, close]);

  const hits = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q || !map) return [];
    return map.articles.filter((a) =>
      `${a.title} ${a.summary}`.toLowerCase().includes(q),
    );
  }, [map, query]);

  const related = routeKeys.filter((key) => key !== resolvedKey);
  const titleOf = (key: string) =>
    map?.articles.find((a) => a.key === key)?.title ?? key;

  if (!isOpen) return null;
  const searching = query.trim().length > 0;

  return (
    <aside
      className="help-panel"
      role="dialog"
      aria-modal="false"
      aria-label={t("title")}
      data-testid="help-panel"
    >
      <header className="help-panel-head">
        <BookOpen size={15} aria-hidden="true" />
        <div className="help-panel-head-title">
          {article && !searching ? article.title : t("title")}
        </div>
        <button
          type="button"
          className="icon-btn"
          aria-label={t("close")}
          onClick={close}
          style={{ width: 28, height: 28 }}
        >
          <X size={15} />
        </button>
      </header>

      <label className="help-panel-search">
        <Search size={13} aria-hidden="true" />
        <input
          type="search"
          value={query}
          placeholder={t("search")}
          aria-label={t("search")}
          onChange={(event) => {
            setQuery(event.target.value);
          }}
        />
      </label>

      <div className="help-panel-body">
        {searching && (
          <ul className="help-panel-list" data-testid="help-search-hits">
            {hits.length === 0 && (
              <li className="help-panel-muted">{t("noHits")}</li>
            )}
            {hits.map((hit) => (
              <li key={hit.key}>
                <button
                  type="button"
                  onClick={() => {
                    setQuery("");
                    open(hit.key);
                  }}
                >
                  <strong>{hit.title}</strong>
                  <span>{hit.summary}</span>
                </button>
              </li>
            ))}
          </ul>
        )}

        {!searching && articleKey && routeKeys[0] !== articleKey && (
          <button
            type="button"
            className="help-panel-back"
            onClick={() => {
              open();
            }}
          >
            <ArrowLeft size={13} /> {t("backToScreen")}
          </button>
        )}

        {!searching && isLoading && (
          <div className="help-panel-muted" data-testid="help-loading">
            <Spinner size="sm" />
          </div>
        )}

        {!searching && !resolvedKey && (
          <p className="help-panel-muted" data-testid="help-no-article">
            {mapError ? t("loadError") : t("noArticle")}
          </p>
        )}

        {!searching && isError && (
          <p className="help-panel-muted">{t("loadError")}</p>
        )}

        {!searching && article && (
          <>
            <p className="help-panel-summary">{article.summary}</p>
            <ArticleBody article={article} focusStep={focusStep} />
          </>
        )}

        {!searching && related.length > 0 && (
          <div className="help-panel-related">
            <div className="help-panel-related-title">{t("related")}</div>
            <ul className="help-panel-list">
              {related.map((key) => (
                <li key={key}>
                  <button
                    type="button"
                    onClick={() => {
                      open(key);
                    }}
                  >
                    <strong>{titleOf(key)}</strong>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      <footer className="help-panel-foot">
        {/* Новая вкладка: панель нужна, чтобы выполнять шаги на ЭТОМ экране, не уходя с него. */}
        <a
          href={article?.url ?? helpApi.siteUrl(lang)}
          target="_blank"
          rel="noreferrer"
        >
          {article ? t("openArticle") : t("openSite")}
          <ExternalLink size={12} aria-hidden="true" />
        </a>
      </footer>
    </aside>
  );
};
