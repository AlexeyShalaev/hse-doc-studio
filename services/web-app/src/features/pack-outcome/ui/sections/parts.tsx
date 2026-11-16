import { useId, useState, type ReactNode } from "react";
import { ChevronDown, ChevronRight, Search, TriangleAlert } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { EmptyStep } from "../../lib/routeSteps";
import type { OutcomeSelection } from "../../lib/urlState";
import { useOutcomeModel } from "../../model";
import { useRuleEdit } from "../edit/context";
import { useIsSelected } from "./helpers";

/** Строка-счётчик вверху секции: «В комплекте 12», «Выключено 1». Только числа из ответа. */
export const Stats = ({
  items,
  testId,
}: {
  items: { id: string; label: string; value: number }[];
  testId?: string;
}) => (
  <ul className="po-stats" data-testid={testId}>
    {items.map((item) => (
      <li
        key={item.id}
        className="po-stat"
        data-zero={item.value === 0 ? "true" : undefined}
        data-testid={`${testId ?? "stat"}-${item.id}`}
      >
        <span className="po-stat-value">{item.value}</span>
        <span className="po-stat-label">{item.label}</span>
      </li>
    ))}
  </ul>
);

/** Поиск и фильтры секции: список элементов длинный, искать нужно по названию и по id. */
export const FilterBar = ({
  label,
  query,
  onQuery,
  testId,
  children,
}: {
  label: string;
  query: string;
  onQuery: (next: string) => void;
  testId: string;
  children?: ReactNode;
}) => {
  const { t } = useTranslation("packOutcome");
  return (
    <div className="po-filters" role="search" aria-label={label}>
      <label className="po-search">
        <Search size="0.8125rem" aria-hidden="true" />
        <input
          type="search"
          className="input"
          placeholder={t("filters.search")}
          aria-label={t("filters.searchIn", { name: label })}
          value={query}
          data-testid={`${testId}-search`}
          onChange={(e) => {
            onQuery(e.target.value);
          }}
        />
      </label>
      {children}
    </div>
  );
};

/** Свёрнутый блок («Не в этой комбинации»): состояние локальное, при поиске раскрывается. */
export const Disclosure = ({
  label,
  count,
  forceOpen = false,
  testId,
  children,
}: {
  label: string;
  count: number;
  forceOpen?: boolean;
  testId: string;
  children: ReactNode;
}) => {
  const [local, setLocal] = useState(false);
  const open = local || forceOpen;
  const id = useId();
  const Chevron = open ? ChevronDown : ChevronRight;
  return (
    <div className="po-disc" data-testid={testId}>
      <button
        type="button"
        className="po-disc-btn"
        aria-expanded={open}
        aria-controls={id}
        data-testid={`${testId}-toggle`}
        onClick={() => {
          setLocal(!open);
        }}
      >
        <Chevron size="0.875rem" aria-hidden="true" />
        <span>{label}</span>
        <span className="po-disc-count">{count}</span>
      </button>
      <div id={id} className="po-disc-body" hidden={!open}>
        {open && children}
      </div>
    </div>
  );
};

type PickButtonProps = {
  el: OutcomeSelection;
  /** Заголовок карточки: имя элемента. */
  title: ReactNode;
  /** Значки справа от заголовка. */
  badges?: ReactNode;
  /** Описание под заголовком: читается программой экрана как пояснение. */
  children?: ReactNode;
  testId?: string;
};

/**
 * Кнопка выбора элемента результата. Клик пишет `selected=раздел:id` в адрес (повторный снимает);
 * в кнопке только строчные элементы, поэтому вложенные списки живут снаружи, а имя берётся из
 * заголовка (`aria-labelledby`), остальное идёт пояснением.
 */
export const PickButton = ({
  el,
  title,
  badges,
  children,
  testId,
}: PickButtonProps) => {
  const { select } = useOutcomeModel();
  const selected = useIsSelected(el);
  const uid = useId();
  return (
    <button
      type="button"
      className="po-pick"
      data-po-pick="true"
      aria-pressed={selected}
      aria-current={selected ? "true" : undefined}
      aria-labelledby={`${uid}-t`}
      aria-describedby={children ? `${uid}-d` : undefined}
      data-testid={testId}
      onClick={() => {
        select(el);
      }}
    >
      <span className="po-pick-head">
        <span className="po-pick-title" id={`${uid}-t`}>
          {title}
        </span>
        {badges && <span className="po-pick-badges">{badges}</span>}
      </span>
      {children && (
        <span className="po-pick-body" id={`${uid}-d`}>
          {children}
        </span>
      )}
    </button>
  );
};

/** Элемент списка с кнопкой выбора; `muted` приглушает отсутствующий или выключенный. */
export const PickItem = ({
  muted = false,
  testId,
  ...props
}: PickButtonProps & { muted?: boolean }) => {
  const selected = useIsSelected(props.el);
  // Элемент изменился после правки по месту: полоса на несколько секунд.
  const flash = useRuleEdit()?.flashed.has(
    `${props.el.section}:${props.el.id}`,
  );
  return (
    <li
      className="po-item"
      data-muted={muted ? "true" : undefined}
      data-selected={selected ? "true" : undefined}
      data-flash={flash ? "true" : undefined}
      data-testid={testId}
    >
      <PickButton {...props} />
    </li>
  );
};

/** Строка причины: «нет: вид работы: сейчас проектный, нужно исследовательский». */
export const Reason = ({
  prefix,
  texts,
}: {
  prefix?: string;
  texts: string[];
}) => (
  <span className="po-reason">
    {prefix && <span className="po-reason-prefix">{prefix}</span>}
    {texts.join("; ")}
  </span>
);

/** Заголовок подгруппы внутри секции. */
export const GroupTitle = ({
  id,
  children,
  count,
}: {
  id: string;
  children: ReactNode;
  count?: number;
}) => (
  <h4 className="po-group-title" id={id}>
    {children}
    {count !== undefined && <span className="po-group-count">{count}</span>}
  </h4>
);

/**
 * Предупреждение «Нет человека для шага маршрута»: общее для секций «Участники» и «Маршрут
 * подписания». Список шагов считает `emptySteps` из ответа сервера; пустой список ничего не рисует.
 */
export const StepWarning = ({
  steps,
  testId,
}: {
  steps: readonly EmptyStep[];
  testId: string;
}) => {
  const { t } = useTranslation("packOutcome");
  if (steps.length === 0) return null;
  return (
    <div
      className="po-warn"
      role="group"
      aria-label={t("route.warnTitle")}
      data-testid={testId}
    >
      <TriangleAlert size="1rem" aria-hidden="true" className="po-warn-icon" />
      <div>
        <p className="po-warn-title">{t("route.warnTitle")}</p>
        <ul className="po-warn-list">
          {steps.map((s) => (
            <li key={`${s.pointId}:${String(s.step)}`}>
              {t("route.warnStep", {
                point: s.pointName,
                step: s.step,
                who: s.personas.join(", "),
              })}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
};
