import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { useTranslation } from "react-i18next";
import {
  ChevronRight,
  CornerLeftUp,
  File,
  Folder,
  FolderPlus,
  FolderX,
  FileSearch,
  Loader2,
  Search,
  SearchX,
  X,
  XCircle,
} from "lucide-react";
import type { ProbeFolderResult } from "@entities/setup";
import {
  filterEntries,
  joinPath,
  parentPath,
  toCrumbs,
} from "@features/first-run-setup";

type FolderBrowserProps = {
  path: string;
  probe: ProbeFolderResult | null;
  isLoading: boolean;
  onNavigate: (path: string) => void;
};

/** Со скольких подпапок список становится длиннее одного экрана. */
const FILTER_HINT_THRESHOLD = 12;
/** Сколько файлов показываем как подсказку «это та самая папка». */
const FILE_PREVIEW_LIMIT = 12;

/**
 * Обзор файловой системы ХОСТА прямо из контейнера.
 *
 * Мышкой в проводник отсюда не ткнуть, поэтому каждый шаг — одноразовый
 * контейнер с бинд-маунтом: секунда-полторы на переход. Это дороже обычного
 * листинга, зато человек выбирает папку глазами, а не печатает путь вслепую и
 * не гадает, не опечатался ли.
 *
 * Отбор по имени работает по УЖЕ полученному списку и потому мгновенен. Вглубь
 * он не ищет намеренно: обход десятка каталогов стоил бы десятка контейнеров, а
 * решаемая задача другая — в домашней папке под сотню подпапок, и мотать её
 * мышкой долго.
 */
export const FolderBrowser = ({
  path,
  probe,
  isLoading,
  onNavigate,
}: FolderBrowserProps) => {
  const { t } = useTranslation("setup");
  const [query, setQuery] = useState("");
  const [shownPath, setShownPath] = useState(path);
  const filterRef = useRef<HTMLInputElement>(null);

  // Перешли в другую папку — отбор сбрасываем. Иначе человек открывает папку и
  // видит пустоту, потому что прежний запрос ни к чему в ней не подходит.
  if (path !== shownPath) {
    setShownPath(path);
    setQuery("");
  }

  const crumbs = toCrumbs(path);
  const parent = parentPath(path);
  const all = probe?.entries ?? [];
  const matched = filterEntries(all, query);
  const folders = matched.filter((entry) => entry.is_dir);
  const files = matched.filter((entry) => !entry.is_dir);
  const probeFailed = probe !== null && probe.status !== "ok";
  const missing = probe?.status === "ok" && !probe.exists;
  const filtering = query.trim() !== "";
  const nothingMatched = filtering && matched.length === 0;

  const handleFilterKeys = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter") {
      event.preventDefault();
      // Только при активном отборе. Поле в фокусе с самого открытия, и рефлекс
      // «Enter = далее» иначе уносил бы в первую попавшуюся папку списка.
      const first = filtering ? folders[0] : undefined;
      if (first) onNavigate(joinPath(path, first.name));
    }
    if (event.key === "Escape" && query !== "") {
      // Гасим здесь: иначе Escape уйдёт выше и закроет что-нибудь ещё.
      event.stopPropagation();
      setQuery("");
    }
  };

  return (
    <div className="setup-browser">
      {/* Хлебные крошки: любой сегмент — ссылка наверх, это самый быстрый
          способ вернуться, когда ушёл не туда. */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          flexWrap: "wrap",
          gap: "0.125rem",
          padding: "0.4375rem 0.625rem",
          borderBottom: "1px solid var(--border)",
          fontSize: "0.75rem",
          minHeight: "2.125rem",
        }}
      >
        {crumbs.map((crumb, index) => (
          <span
            key={crumb.path}
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "0.125rem",
            }}
          >
            {index > 0 && (
              <ChevronRight
                size="0.6875rem"
                style={{ opacity: 0.35, flexShrink: 0 }}
              />
            )}
            <button
              type="button"
              className="btn ghost xs"
              disabled={index === crumbs.length - 1}
              onClick={() => {
                onNavigate(crumb.path);
              }}
              style={{
                padding: "1px 0.3125rem",
                fontWeight: index === crumbs.length - 1 ? 600 : 400,
                opacity: index === crumbs.length - 1 ? 1 : 0.75,
              }}
            >
              {crumb.label}
            </button>
          </span>
        ))}
        {isLoading && (
          <Loader2
            className="spin"
            size="0.75rem"
            style={{ marginLeft: "auto", opacity: 0.5, flexShrink: 0 }}
          />
        )}
      </div>

      <FilterField
        inputRef={filterRef}
        value={query}
        placeholder={
          all.length > FILTER_HINT_THRESHOLD
            ? t("browser.filterCount", { count: all.length })
            : t("browser.filter")
        }
        matched={filtering ? matched.length : null}
        onChange={setQuery}
        onKeyDown={handleFilterKeys}
      />

      <div className="setup-browser-list">
        {parent !== null && (
          <Row
            icon={<CornerLeftUp size="0.875rem" style={{ opacity: 0.6 }} />}
            label=".."
            dim
            onClick={() => {
              onNavigate(parent);
            }}
          />
        )}

        {probeFailed && (
          <Note
            icon={
              <XCircle size="0.9375rem" style={{ color: "var(--c-err)" }} />
            }
            title={t(`browser.failed.${probe.reason ?? probe.status}.title`, {
              defaultValue: t("browser.failed.unknown.title"),
            })}
            hint={t(`browser.failed.${probe.reason ?? probe.status}.hint`, {
              defaultValue: t("browser.failed.unknown.hint"),
            })}
          />
        )}

        {missing && (
          <Note
            icon={
              <FolderX size="0.9375rem" style={{ color: "var(--c-warn)" }} />
            }
            title={t("browser.missing.title")}
            hint={t("browser.missing.hint")}
          />
        )}

        {nothingMatched && (
          <Note
            icon={<SearchX size="0.9375rem" style={{ opacity: 0.5 }} />}
            title={t("browser.noMatches.title", { query: query.trim() })}
            hint={t("browser.noMatches.hint")}
          />
        )}

        {filtering && folders.length === 0 && files.length > 0 && (
          <Note
            icon={<FileSearch size="0.9375rem" style={{ opacity: 0.5 }} />}
            title={t("browser.filesOnly.title")}
            hint={t("browser.filesOnly.hint")}
          />
        )}

        {!missing &&
          !probeFailed &&
          !filtering &&
          folders.length === 0 &&
          !isLoading && (
            <Note
              icon={<FolderPlus size="0.9375rem" style={{ opacity: 0.5 }} />}
              title={t("browser.noSubfolders.title")}
              hint={t("browser.noSubfolders.hint")}
            />
          )}

        {folders.map((entry) => (
          <Row
            key={entry.name}
            icon={<Folder size="0.875rem" style={{ color: "var(--c-info)" }} />}
            label={entry.name}
            highlight={query}
            onClick={() => {
              onNavigate(joinPath(path, entry.name));
            }}
          />
        ))}

        {/* Файлы не выбираются, но показать их важно: именно по знакомым
            именам человек убеждается, что это его папка. */}
        {files.slice(0, FILE_PREVIEW_LIMIT).map((entry) => (
          <Row
            key={entry.name}
            icon={<File size="0.8125rem" style={{ opacity: 0.35 }} />}
            label={entry.name}
            highlight={query}
            dim
          />
        ))}
        {files.length > FILE_PREVIEW_LIMIT && (
          <div
            className="dim"
            style={{
              padding: "0.375rem 0.75rem 0.625rem 2.125rem",
              fontSize: "0.6875rem",
            }}
          >
            {t("browser.moreFiles", {
              count: files.length - FILE_PREVIEW_LIMIT,
            })}
          </div>
        )}
      </div>
    </div>
  );
};

type FilterFieldProps = {
  inputRef: React.RefObject<HTMLInputElement | null>;
  value: string;
  placeholder: string;
  /** Сколько элементов подошло; null — отбор не задан. */
  matched: number | null;
  onChange: (value: string) => void;
  onKeyDown: (event: KeyboardEvent<HTMLInputElement>) => void;
};

const FilterField = ({
  inputRef,
  value,
  placeholder,
  matched,
  onChange,
  onKeyDown,
}: FilterFieldProps) => {
  const { t } = useTranslation("setup");

  // Фокус сразу: набрать пару букв быстрее, чем целиться мышкой в поле, а
  // выбор папки — единственное, чем здесь вообще занимаются.
  useEffect(() => {
    inputRef.current?.focus();
  }, [inputRef]);

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: "0.4375rem",
        padding: "0.3125rem 0.625rem",
        borderBottom: "1px solid var(--border)",
      }}
    >
      <Search size="0.8125rem" style={{ opacity: 0.45, flexShrink: 0 }} />
      <input
        ref={inputRef}
        value={value}
        placeholder={placeholder}
        spellCheck={false}
        autoComplete="off"
        aria-label={t("browser.filter")}
        className="setup-filter"
        onChange={(event) => {
          onChange(event.target.value);
        }}
        onKeyDown={onKeyDown}
        style={{
          flex: 1,
          minWidth: 0,
          border: "none",
          background: "transparent",
          color: "inherit",
          font: "inherit",
          fontSize: "0.78125rem",
          outline: "none",
          padding: "0.125rem 0",
        }}
      />
      {matched !== null && (
        <>
          <span
            className="dim"
            aria-live="polite"
            style={{ fontSize: "0.6875rem", flexShrink: 0 }}
          >
            {t("browser.matched", { count: matched })}
          </span>
          <button
            type="button"
            className="btn ghost xs"
            aria-label={t("browser.clearFilter")}
            onClick={() => {
              onChange("");
              inputRef.current?.focus();
            }}
            style={{ padding: "1px 0.25rem", flexShrink: 0 }}
          >
            <X size="0.6875rem" />
          </button>
        </>
      )}
    </div>
  );
};

type RowProps = {
  icon: React.ReactNode;
  label: string;
  /** Подсветить эту подстроку — видно, почему строка попала в отбор. */
  highlight?: string | undefined;
  dim?: boolean | undefined;
  onClick?: (() => void) | undefined;
};

const Row = ({ icon, label, highlight, dim = false, onClick }: RowProps) => {
  const interactive = onClick !== undefined;
  return (
    <button
      type="button"
      className={interactive ? "setup-row" : undefined}
      disabled={!interactive}
      onClick={onClick}
      style={{
        display: "flex",
        alignItems: "center",
        gap: "0.5625rem",
        width: "100%",
        padding: "0.375rem 0.75rem",
        border: "none",
        background: "transparent",
        color: "inherit",
        font: "inherit",
        fontSize: "0.8125rem",
        textAlign: "left",
        cursor: interactive ? "pointer" : "default",
        opacity: dim ? 0.55 : 1,
      }}
    >
      <span style={{ display: "flex", flexShrink: 0 }}>{icon}</span>
      <span
        style={{
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
        }}
      >
        <Highlighted text={label} needle={highlight ?? ""} />
      </span>
    </button>
  );
};

/** Имя с подсвеченным совпадением: сразу видно, почему строка осталась в списке. */
const Highlighted = ({ text, needle }: { text: string; needle: string }) => {
  const query = needle.trim();
  if (query === "") return <>{text}</>;
  const at = text.toLocaleLowerCase().indexOf(query.toLocaleLowerCase());
  if (at < 0) return <>{text}</>;
  return (
    <>
      {text.slice(0, at)}
      <mark
        style={{
          background: "var(--c-info-soft)",
          color: "var(--c-info)",
          borderRadius: "0.1875rem",
          padding: "0 1px",
        }}
      >
        {text.slice(at, at + query.length)}
      </mark>
      {text.slice(at + query.length)}
    </>
  );
};

type NoteProps = {
  icon: React.ReactNode;
  title: string;
  hint: string;
};

const Note = ({ icon, title, hint }: NoteProps) => (
  <div
    style={{ display: "flex", gap: "0.5625rem", padding: "0.875rem 0.75rem" }}
  >
    <span style={{ flexShrink: 0, marginTop: 1 }}>{icon}</span>
    <div>
      <div style={{ fontSize: "0.8125rem", fontWeight: 600 }}>{title}</div>
      <div
        className="dim"
        style={{ fontSize: "0.75rem", marginTop: "0.125rem" }}
      >
        {hint}
      </div>
    </div>
  </div>
);
