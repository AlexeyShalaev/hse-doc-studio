import { createContext, useContext, useId, type ReactNode } from "react";
import { ChevronDown, ChevronRight, Plus } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useSpace } from "../context/SpaceContext";
import { useSituation } from "../context/useSituation";
import type { ChangeSymbol } from "../situation/deltaSummary";
import { useSpaceNav } from "../context/useSpaceNav";
import { useParts } from "./partsStore";
import type { Reason, ShowAction } from "./reasons";
import "./space-result.css";

/** Что изменилось после смены условия: ключи `<раздел>:<id>` как у `sel` (`useSituationDelta`). */
export type RowDelta = {
  changed: ReadonlyMap<string, ChangeSymbol>;
  highlight: boolean;
  onlyChanged: boolean;
};
export const DeltaContext = createContext<RowDelta | null>(null);

/**
 * Знак изменения строки. Точка сдачи и порядок подписей это целая строка, а сервер отдаёт изменения
 * по их пунктам и шагам (`route:<точка>/step/2`): такая строка считается изменённой.
 */
const changeOf = (
  changed: ReadonlyMap<string, ChangeSymbol>,
  sel: string,
): ChangeSymbol | undefined => {
  const own = changed.get(sel);
  if (own !== undefined || !/^(points|route):[^/]+$/.test(sel)) return own;
  for (const key of changed.keys()) {
    if (key.startsWith(`${sel}/`)) return "~";
  }
  return undefined;
};

/** Состояние строки относительно последней смены условия; `hidden`: «только изменившееся». */
export const useRowDelta = (
  sel: string,
): { change: ChangeSymbol | undefined; flash: boolean; hidden: boolean } => {
  const delta = useContext(DeltaContext);
  const change = delta ? changeOf(delta.changed, sel) : undefined;
  return {
    change,
    flash: delta?.highlight === true && change !== undefined,
    hidden: delta?.onlyChanged === true && change === undefined,
  };
};

/** Выбрана ли строка: `sel` из адреса. Нажатие выбирает, повторное нажатие снимает выбор. */
export const useRowSelection = (
  sel: string,
): { selected: boolean; toggle: () => void } => {
  const { selection } = useSpace();
  const nav = useSpaceNav();
  const selected = selection === sel;
  return {
    selected,
    toggle: () => {
      nav.go({ sel: selected ? null : sel });
    },
  };
};

/**
 * Строка части результата: значок, название, пояснение и бейджи. Вся левая часть это одна кнопка
 * выбора (в правой колонке откроются подробности), справа место для действий строки.
 */
export const PickRow = ({
  sel,
  icon,
  title,
  sub,
  badges,
  trailing,
  muted = false,
  testId,
}: {
  sel: string;
  icon: ReactNode;
  title: string;
  sub?: ReactNode;
  badges?: ReactNode;
  trailing?: ReactNode;
  muted?: boolean;
  testId: string;
}) => {
  const { selected, toggle } = useRowSelection(sel);
  const { t } = useTranslation("packSpace");
  const { change, flash, hidden } = useRowDelta(sel);
  if (hidden) return null;
  return (
    <li
      className="sp-row"
      data-change={change}
      data-flash={flash ? "true" : undefined}
      data-selected={selected ? "true" : undefined}
      data-muted={muted ? "true" : undefined}
      data-testid={testId}
    >
      <button
        type="button"
        className="sp-row-pick"
        aria-pressed={selected}
        onClick={toggle}
      >
        <span className="sp-row-icon" aria-hidden="true">
          {icon}
        </span>
        <span className="sp-row-text">
          <span className="sp-row-name">
            <span className="sp-row-title">{title}</span>
            {change === "+" ? (
              <span className="chip accent sp-badge" data-testid="sp-new">
                {t("result.delta.added")}
              </span>
            ) : null}
            {badges}
          </span>
          {sub ? <span className="sp-row-sub">{sub}</span> : null}
        </span>
      </button>
      {trailing ? <span className="sp-row-acts">{trailing}</span> : null}
    </li>
  );
};

/** Кнопка «Показать при …»: ставит условие студента, при котором элемент вернётся. */
export const ShowButton = ({
  action,
  name,
}: {
  action: ShowAction;
  name: string;
}) => {
  const { t } = useTranslation("packSpace");
  const situation = useSituation();
  const label = t("result.missing.show", { condition: action.label });
  return (
    <button
      type="button"
      className="btn sm sp-show"
      aria-label={t("result.missing.showFor", {
        condition: action.label,
        name,
      })}
      title={label}
      onClick={() => {
        situation.setInput(action.input, action.value);
      }}
    >
      <Plus size="0.8125rem" aria-hidden="true" />
      <span className="sp-show-text">{label}</span>
    </button>
  );
};

/** Одна строка «Не вошло»: название, причина словами и, если есть, действие. */
export type MissingRow = {
  key: string;
  sel: string;
  icon: ReactNode;
  title: string;
  reason: Reason | null;
  fallback: string;
  testId: string;
};

/**
 * «Не вошло в комплект · N»: свёрнутая строка, под ней элементы, которых нет при этих условиях,
 * каждый с причиной простыми словами. Одна и та же для документов, данных, участников и сдачи.
 */
export const Missing = ({
  title,
  rows: all,
  open: forced = false,
  testId,
}: {
  title: string;
  rows: readonly MissingRow[];
  /** Раскрыта принудительно (например, идёт поиск). */
  open?: boolean;
  testId: string;
}) => {
  // Раскрытость «Не вошло» запоминается: человек, который ищет причины, не раскрывает заново.
  const parts = useParts();
  const local = parts.isMissingOpen(testId);
  const id = useId();
  const delta = useContext(DeltaContext);
  // «Только изменившееся»: в «Не вошло» остаются строки, которые изменились (например, пропали).
  const shown = delta?.onlyChanged
    ? all.filter((row) => delta.changed.has(row.sel))
    : all;
  if (shown.length === 0) return null;
  const open = local || forced;
  const Chevron = open ? ChevronDown : ChevronRight;
  return (
    <div className="sp-missing" data-testid={testId}>
      <button
        type="button"
        className="sp-missing-head"
        aria-expanded={open}
        aria-controls={id}
        data-testid={`${testId}-toggle`}
        onClick={() => {
          parts.toggleMissing(testId);
        }}
      >
        <Chevron size="0.875rem" aria-hidden="true" />
        <span>{title}</span>
        <span className="sp-count">{shown.length}</span>
      </button>
      <ul id={id} className="sp-rows" hidden={!open}>
        {open
          ? shown.map((row) => (
              <PickRow
                key={row.key}
                sel={row.sel}
                icon={row.icon}
                title={row.title}
                sub={row.reason?.text ?? row.fallback}
                muted
                trailing={
                  row.reason?.action ? (
                    <ShowButton action={row.reason.action} name={row.title} />
                  ) : undefined
                }
                testId={row.testId}
              />
            ))
          : null}
      </ul>
    </div>
  );
};

/** Заголовок подгруппы в части: «ЕСПД · 5». */
export const GroupLabel = ({
  id,
  children,
  count,
}: {
  id: string;
  children: ReactNode;
  count: number;
}) => (
  <h3 className="sp-group" id={id}>
    {children}
    <span className="sp-count">{count}</span>
  </h3>
);
