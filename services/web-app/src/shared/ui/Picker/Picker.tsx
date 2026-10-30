import {
  useEffect,
  useId,
  useRef,
  useState,
  type KeyboardEvent,
  type ReactNode,
} from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import {
  Building2,
  Check,
  ChevronDown,
  FileText,
  Search,
  Server,
  Users,
  X,
} from "lucide-react";
import { clsx } from "clsx";
import { useTranslation } from "react-i18next";
import { useDebouncedValue } from "../../lib/useDebouncedValue";
import {
  PICKER_LIMIT,
  SEARCH_DEBOUNCE_MS,
  SEARCH_MAX_LENGTH,
  type PickerItem,
  type PickerPage,
} from "../../lib/serverList/types";
import { Avatar } from "../PersonCell";
import { Popover, PopoverContent, PopoverTrigger } from "../Popover";
import { Spinner } from "../Spinner";
import { FilterTriggerText } from "../FilterBar/FilterMenu";

// Выбор человека, организации, группы, проекта или раннера поиском на сервере.
// Сервер отдаёт до 20 первых совпадений и has_more; листания нет, при has_more
// пикер просит уточнить поиск. Клавиатура: стрелки, Enter выбирает, Esc
// закрывает. Источник (PickerSource) задаёт, куда идёт запрос: пикер видит
// только то, что вызывающему можно видеть.

export type PickerSource = {
  /** Начало ключа запроса: свой у каждого источника и его параметров. */
  key: readonly unknown[];
  search: (
    q: string,
    options: { limit: number; signal: AbortSignal },
  ) => Promise<PickerPage>;
  /**
   * Имя по id: фильтр, открытый по ссылке, знает только id из адреса.
   * Без него на кнопке нейтральная подпись «выбрано».
   */
  resolve?: (id: string, signal: AbortSignal) => Promise<PickerItem | null>;
};

const KIND_ICON: Record<Exclude<PickerItem["kind"], "user">, ReactNode> = {
  org: <Building2 size={14} aria-hidden="true" />,
  group: <Users size={14} aria-hidden="true" />,
  project: <FileText size={14} aria-hidden="true" />,
  runner: <Server size={14} aria-hidden="true" />,
};

/** Значок строки: аватар человека или значок вида. */
export const PickerItemIcon = ({ item }: { item: PickerItem }) =>
  item.kind === "user" ? (
    <Avatar name={item.name} seed={item.id} size={20} />
  ) : (
    <span className="picker-kind" aria-hidden="true">
      {KIND_ICON[item.kind]}
    </span>
  );

export type PickerPanelProps = {
  source: PickerSource;
  onSelect: (item: PickerItem) => void;
  selectedId?: string | null | undefined;
  placeholder?: string | undefined;
  /** Подпись поля для скринридера. */
  label: string;
  /** Текст, когда ничего не нашлось. */
  emptyText?: string | undefined;
  testId?: string | undefined;
};

/** Поле поиска и список совпадений: содержимое Picker и PickerFilter. */
export const PickerPanel = ({
  source,
  onSelect,
  selectedId = null,
  placeholder,
  label,
  emptyText,
  testId,
}: PickerPanelProps) => {
  const { t } = useTranslation("uiPrimitives");
  const [text, setText] = useState("");
  const q = useDebouncedValue(text.trim(), SEARCH_DEBOUNCE_MS);
  // Выделенная строка привязана к ответу: новый ответ начинает с первой.
  const [cursor, setCursor] = useState({ list: "", index: 0 });
  const listId = useId();
  const listRef = useRef<HTMLUListElement>(null);
  const result = useQuery({
    queryKey: [...source.key, "picker", q],
    queryFn: ({ signal }) => source.search(q, { limit: PICKER_LIMIT, signal }),
    placeholderData: keepPreviousData,
    staleTime: 30_000,
  });
  const items = result.data?.items ?? [];
  const typing = text.trim() !== q;
  const busy = result.isFetching || typing;
  const list = `${q}:${String(result.dataUpdatedAt)}`;
  const active = cursor.list === list ? cursor.index : 0;
  const setActive = (next: number | ((index: number) => number)) => {
    setCursor({
      list,
      index: typeof next === "function" ? next(active) : next,
    });
  };

  useEffect(() => {
    const node = listRef.current?.querySelector<HTMLElement>(
      `[data-index="${String(active)}"]`,
    );
    // В jsdom прокрутки нет: проверяем, что метод есть.
    if (node && "scrollIntoView" in node)
      node.scrollIntoView({ block: "nearest" });
  }, [active]);

  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActive((i) => Math.min(items.length - 1, i + 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActive((i) => Math.max(0, i - 1));
    } else if (event.key === "PageDown") {
      event.preventDefault();
      setActive(Math.max(0, items.length - 1));
    } else if (event.key === "PageUp") {
      event.preventDefault();
      setActive(0);
    } else if (event.key === "Enter") {
      event.preventDefault();
      const item = items[active];
      if (item && !typing) onSelect(item);
    }
  };

  const optionId = (index: number) => `${listId}-${String(index)}`;
  const current = items[active];

  return (
    <div className="picker-panel" data-testid={testId}>
      <div className="picker-search">
        <Search size={14} aria-hidden="true" />
        <input
          role="combobox"
          aria-expanded="true"
          aria-controls={listId}
          aria-autocomplete="list"
          aria-activedescendant={current ? optionId(active) : undefined}
          aria-label={label}
          className="picker-input"
          value={text}
          maxLength={SEARCH_MAX_LENGTH}
          placeholder={placeholder ?? t("picker.searchPlaceholder")}
          autoFocus
          onChange={(event) => {
            setText(event.target.value);
          }}
          onKeyDown={onKeyDown}
        />
        {busy && <Spinner size="sm" />}
      </div>
      <ul
        id={listId}
        ref={listRef}
        role="listbox"
        aria-label={label}
        aria-busy={busy}
        className="picker-list"
      >
        {result.isPending && (
          <li className="picker-note" role="presentation">
            {t("picker.loading")}
          </li>
        )}
        {result.isError && (
          <li className="picker-note is-error" role="presentation">
            {t("picker.error")}
          </li>
        )}
        {result.isSuccess && items.length === 0 && !typing && (
          <li className="picker-note" role="presentation">
            {emptyText ?? (q ? t("picker.noMatches") : t("picker.nothing"))}
          </li>
        )}
        {items.map((item, index) => (
          <li
            key={`${item.kind}:${item.id}`}
            id={optionId(index)}
            role="option"
            aria-selected={index === active}
            data-index={index}
            className={clsx("picker-option", index === active && "is-active")}
            onMouseMove={() => {
              if (index !== active) setActive(index);
            }}
            onMouseDown={(event) => {
              // Фокус остаётся в поле: иначе поповер теряет его до выбора.
              event.preventDefault();
            }}
            onClick={() => {
              onSelect(item);
            }}
          >
            <PickerItemIcon item={item} />
            <span className="picker-option-text">
              <span className="picker-option-name">{item.name}</span>
              {item.detail && (
                <span className="picker-option-detail">{item.detail}</span>
              )}
            </span>
            {item.id === selectedId && (
              <Check size={14} aria-hidden="true" className="combo-check" />
            )}
          </li>
        ))}
      </ul>
      {result.data?.has_more && (
        <p className="picker-more" role="note">
          {t("picker.refine", { limit: PICKER_LIMIT })}
        </p>
      )}
    </div>
  );
};

export type PickerProps = {
  source: PickerSource;
  value: PickerItem | null;
  onChange: (item: PickerItem | null) => void;
  /** Подпись поля для скринридера и заголовок списка. */
  label: string;
  placeholder?: string | undefined;
  searchPlaceholder?: string | undefined;
  emptyText?: string | undefined;
  disabled?: boolean | undefined;
  /** Крестик, который снимает выбор. */
  clearable?: boolean | undefined;
  id?: string | undefined;
  className?: string | undefined;
  testId?: string | undefined;
};

/** Поле формы: показывает выбранное, по нажатию открывает поиск. */
export const Picker = ({
  source,
  value,
  onChange,
  label,
  placeholder,
  searchPlaceholder,
  emptyText,
  disabled = false,
  clearable = false,
  id,
  className,
  testId,
}: PickerProps) => {
  const { t } = useTranslation("uiPrimitives");
  const [open, setOpen] = useState(false);
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <span className={clsx("picker-field", className)}>
        <PopoverTrigger asChild>
          <button
            type="button"
            id={id}
            className="input picker-trigger"
            disabled={disabled}
            aria-haspopup="listbox"
            aria-label={value ? `${label}: ${value.name}` : label}
            data-testid={testId}
          >
            {value ? (
              <>
                <PickerItemIcon item={value} />
                <span className="picker-trigger-text">{value.name}</span>
                {value.detail && (
                  <span className="picker-trigger-detail">{value.detail}</span>
                )}
              </>
            ) : (
              <span className="picker-trigger-text dim">
                {placeholder ?? t("picker.placeholder")}
              </span>
            )}
            <ChevronDown
              size={14}
              aria-hidden="true"
              className="picker-chevron"
            />
          </button>
        </PopoverTrigger>
        {clearable && value && !disabled && (
          <button
            type="button"
            className="picker-clear"
            aria-label={t("picker.clear")}
            title={t("picker.clear")}
            onClick={() => {
              onChange(null);
            }}
          >
            <X size={13} aria-hidden="true" />
          </button>
        )}
      </span>
      <PopoverContent
        width={340}
        align="start"
        aria-label={label}
        // Список не уже поля, из которого открыт.
        style={{
          overflowY: "hidden",
          width: "max(320px, var(--radix-popover-trigger-width))",
        }}
      >
        <PickerPanel
          source={source}
          label={label}
          placeholder={searchPlaceholder}
          emptyText={emptyText}
          selectedId={value?.id ?? null}
          onSelect={(item) => {
            onChange(item);
            setOpen(false);
          }}
        />
      </PopoverContent>
    </Popover>
  );
};

/**
 * Имя выбранного по id: из последнего выбора, иначе через source.resolve.
 * Нужен фильтрам, которые держат в адресе только id.
 */
export const usePickedItem = (
  source: PickerSource,
  id: string | null,
  picked: PickerItem | null,
): PickerItem | null => {
  const known = picked?.id === id ? picked : null;
  // Источник уже назван в source.key: функция resolve в ключ не входит.
  // eslint-disable-next-line @tanstack/query/exhaustive-deps
  const query = useQuery({
    queryKey: [...source.key, "resolve", id],
    queryFn: ({ signal }) =>
      id && source.resolve ? source.resolve(id, signal) : Promise.resolve(null),
    enabled: id !== null && known === null && source.resolve !== undefined,
    staleTime: 5 * 60_000,
  });
  if (id === null) return null;
  return known ?? query.data ?? null;
};

export type PickerFilterProps = {
  label: string;
  source: PickerSource;
  /** id из адреса; null значит «все». */
  value: string | null;
  onChange: (item: PickerItem | null) => void;
  searchPlaceholder?: string | undefined;
  icon?: ReactNode | undefined;
  testId?: string | undefined;
};

/** Фильтр «Человек», «Организация», «Раннер»: кнопка в панели фильтров и поиск. */
export const PickerFilter = ({
  label,
  source,
  value,
  onChange,
  searchPlaceholder,
  icon,
  testId,
}: PickerFilterProps) => {
  const { t } = useTranslation("uiPrimitives");
  const [open, setOpen] = useState(false);
  const [picked, setPicked] = useState<PickerItem | null>(null);
  const item = usePickedItem(source, value, picked);
  const summary =
    value === null ? null : (item?.name ?? t("picker.selectedOne"));
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <span className={clsx("fmenu", value !== null && "is-active")}>
        <PopoverTrigger asChild>
          <button
            type="button"
            className="fmenu-trigger"
            aria-haspopup="listbox"
            data-testid={testId}
          >
            {icon}
            <FilterTriggerText label={label} summary={summary} />
            <ChevronDown size={13} aria-hidden="true" />
          </button>
        </PopoverTrigger>
        {value !== null && (
          <button
            type="button"
            className="fmenu-clear"
            aria-label={t("filterMenu.clearOne", { label })}
            title={t("filterMenu.clear")}
            onClick={() => {
              setPicked(null);
              onChange(null);
            }}
          >
            <X size={12} aria-hidden="true" />
          </button>
        )}
      </span>
      <PopoverContent
        width={320}
        align="start"
        aria-label={label}
        style={{ overflowY: "hidden" }}
      >
        <PickerPanel
          source={source}
          label={label}
          placeholder={searchPlaceholder}
          selectedId={value}
          onSelect={(next) => {
            setPicked(next);
            onChange(next);
            setOpen(false);
          }}
        />
      </PopoverContent>
    </Popover>
  );
};

Picker.displayName = "Picker";
PickerPanel.displayName = "PickerPanel";
PickerFilter.displayName = "PickerFilter";
