import { useEffect, useRef, useState } from "react";
import { Search, X } from "lucide-react";
import { clsx } from "clsx";
import { useTranslation } from "react-i18next";
import { useDebouncedValue } from "../../lib/useDebouncedValue";
import {
  SEARCH_DEBOUNCE_MS,
  SEARCH_MAX_LENGTH,
} from "../../lib/serverList/types";
import { Spinner } from "../Spinner";

// Поле поиска серверного списка. Текст в поле меняется сразу, а наружу уходит
// после паузы в наборе (300 мс), обрезанный по краям. Enter отправляет сразу,
// крестик и Esc очищают. Пока идёт запрос, справа крутилка.

export type SearchInputProps = {
  /** Принятый поиск (из адреса); внешний сброс возвращает поле к нему. */
  value: string;
  /** Вызывается после паузы, Enter или очистки; значение уже обрезано. */
  onChange: (value: string) => void;
  placeholder?: string | undefined;
  /** Доступное имя поля; по умолчанию «Поиск». */
  label?: string | undefined;
  debounceMs?: number | undefined;
  /** Идёт запрос по этому поиску. */
  busy?: boolean | undefined;
  autoFocus?: boolean | undefined;
  className?: string | undefined;
  testId?: string | undefined;
};

export const SearchInput = ({
  value,
  onChange,
  placeholder,
  label,
  debounceMs = SEARCH_DEBOUNCE_MS,
  busy = false,
  autoFocus = false,
  className,
  testId,
}: SearchInputProps) => {
  const { t } = useTranslation("uiPrimitives");
  const [text, setText] = useState(value);
  const debounced = useDebouncedValue(text, debounceMs);
  const sent = useRef(value);
  const inputRef = useRef<HTMLInputElement>(null);

  // Внешний сброс (кнопка «Сбросить», переход по ссылке) меняет и поле.
  useEffect(() => {
    if (value !== sent.current) {
      sent.current = value;
      setText(value);
    }
  }, [value]);

  const send = (raw: string) => {
    const next = raw.trim();
    if (next === sent.current) return;
    sent.current = next;
    onChange(next);
  };

  useEffect(() => {
    // Отправка только после набора: внешний сброс сюда тоже приходит, но
    // совпадает с уже принятым значением.
    const next = debounced.trim();
    if (next !== sent.current) {
      sent.current = next;
      onChange(next);
    }
  }, [debounced, onChange]);

  const clear = () => {
    setText("");
    send("");
    inputRef.current?.focus();
  };

  return (
    <div className={clsx("search-input", className)}>
      <Search size={14} aria-hidden="true" className="search-input-icon" />
      <input
        ref={inputRef}
        type="search"
        className="input"
        value={text}
        maxLength={SEARCH_MAX_LENGTH}
        autoFocus={autoFocus}
        data-testid={testId}
        onChange={(event) => {
          setText(event.target.value);
        }}
        onKeyDown={(event) => {
          if (event.key === "Enter") {
            event.preventDefault();
            send(text);
          } else if (event.key === "Escape" && text !== "") {
            // Пустое поле отдаёт Esc дальше: закрыть окно, панель.
            event.preventDefault();
            event.stopPropagation();
            clear();
          }
        }}
        placeholder={placeholder ?? t("filterBar.searchPlaceholder")}
        aria-label={label ?? t("filterBar.search")}
      />
      <span className="search-input-end">
        {busy && text.trim() !== "" && <Spinner size="sm" />}
        {text !== "" && (
          <button
            type="button"
            className="search-input-clear"
            aria-label={t("searchInput.clear")}
            title={t("searchInput.clear")}
            onClick={clear}
          >
            <X size={13} aria-hidden="true" />
          </button>
        )}
      </span>
    </div>
  );
};

SearchInput.displayName = "SearchInput";
