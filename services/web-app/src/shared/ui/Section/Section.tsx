import { Children, isValidElement, useId, type ReactNode } from "react";
import { ChevronRight, Lock } from "lucide-react";
import { Link } from "react-router";
import { clsx } from "clsx";
import { useTranslation } from "react-i18next";
import { Tooltip } from "../Tooltip";

// Раздел страницы админки и строка настройки в духе настроек GitHub/Vercel:
// слева название и пояснение, справа элемент управления. На узкой карточке
// строка складывается в столбец (container query в index.css).

export type SectionProps = {
  title?: ReactNode | undefined;
  description?: ReactNode | undefined;
  /** Кнопки в шапке раздела справа. */
  actions?: ReactNode | undefined;
  children?: ReactNode | undefined;
  /** Низ раздела: пояснение слева, кнопки справа. */
  footer?: ReactNode | undefined;
  /** card: карточка с рамкой; plain: только заголовок и содержимое. */
  variant?: "card" | "plain" | undefined;
  /** Содержимое без боковых полей: таблица или список во всю ширину карточки. */
  flush?: boolean | undefined;
  id?: string | undefined;
  testId?: string | undefined;
  className?: string | undefined;
};

export const Section = ({
  title,
  description,
  actions,
  children,
  footer,
  variant = "card",
  flush = false,
  id,
  testId,
  className,
}: SectionProps) => {
  const headingId = useId();
  const hasHead = title != null || actions != null;
  return (
    <section
      id={id}
      className={clsx("adm-section", className)}
      data-variant={variant}
      data-testid={testId}
      aria-labelledby={title != null ? headingId : undefined}
    >
      {hasHead && (
        <div className="adm-section-head">
          <div style={{ flex: 1, minWidth: 0 }}>
            {title != null && <h2 id={headingId}>{title}</h2>}
            {description && <p className="adm-section-desc">{description}</p>}
          </div>
          {actions && (
            <div className="flex items-center" style={{ gap: 8 }}>
              {actions}
            </div>
          )}
        </div>
      )}
      {children != null && (
        <div
          className="adm-section-body"
          data-flush={flush ? "true" : undefined}
          style={hasHead ? undefined : { paddingTop: flush ? 0 : 16 }}
        >
          {children}
        </div>
      )}
      {footer && <div className="adm-section-foot">{footer}</div>}
    </section>
  );
};

export type SettingRowProps = {
  label: ReactNode;
  hint?: ReactNode | undefined;
  /** Элемент управления. */
  children: ReactNode;
  /** id поля: подпись становится <label htmlFor>. */
  htmlFor?: string | undefined;
  /**
   * Значение задано окружением и здесь не меняется: рядом с подписью замок с
   * подсказкой. Строка заменяет стандартный текст подсказки.
   */
  locked?: boolean | string | undefined;
  /** inline: управление справа; stacked: под подписью (радиогруппы, длинные поля). */
  layout?: "inline" | "stacked" | undefined;
  /** end: по правому краю (переключатели); stretch: на всю колонку (поля ввода). */
  align?: "end" | "stretch" | undefined;
  testId?: string | undefined;
};

export const SettingRow = ({
  label,
  hint,
  children,
  htmlFor,
  locked = false,
  layout = "inline",
  align = "end",
  testId,
}: SettingRowProps) => {
  const { t } = useTranslation("uiPrimitives");
  const lockText =
    typeof locked === "string" ? locked : t("adminKit.lockedHint");
  const Label = htmlFor ? "label" : "div";
  return (
    <div
      className="adm-setting"
      data-layout={layout}
      data-locked={locked ? "true" : undefined}
      data-testid={testId}
    >
      <div style={{ minWidth: 0 }}>
        <Label className="adm-setting-label" htmlFor={htmlFor}>
          {label}
          {locked && (
            <Tooltip content={lockText}>
              <span
                className="adm-lock"
                tabIndex={0}
                aria-label={lockText}
                data-testid={testId ? `${testId}-locked` : undefined}
              >
                <Lock size={12} aria-hidden="true" />
                {t("adminKit.locked")}
              </span>
            </Tooltip>
          )}
        </Label>
        {hint && <p className="adm-setting-hint">{hint}</p>}
      </div>
      <div className="adm-setting-control" data-align={align}>
        {children}
      </div>
    </div>
  );
};

export type ListRowTone =
  "neutral" | "success" | "warning" | "danger" | "info" | "accent";

export type ListRowProps = {
  title: ReactNode;
  description?: ReactNode | undefined;
  /** Значок слева в плашке тона. */
  icon?: ReactNode | undefined;
  tone?: ListRowTone | undefined;
  /** Начало строки вместо значка: аватар, точка состояния. */
  leading?: ReactNode | undefined;
  /** Справа: время, число, метка. */
  meta?: ReactNode | undefined;
  /** Адрес: строка становится ссылкой со стрелкой. */
  to?: string | undefined;
  onClick?: (() => void) | undefined;
  testId?: string | undefined;
};

/** Строка списка внутри Section (кладите в <ul className="adm-list"> или SectionList). */
export const ListRow = ({
  title,
  description,
  icon,
  tone = "neutral",
  leading,
  meta,
  to,
  onClick,
  testId,
}: ListRowProps) => {
  const inner = (
    <>
      {leading ??
        (icon && (
          <span className="adm-row-icon" data-tone={tone} aria-hidden="true">
            {icon}
          </span>
        ))}
      <span className="adm-row-text">
        <span className="adm-row-title">{title}</span>
        {description && <span className="adm-row-desc">{description}</span>}
      </span>
      {meta && <span className="adm-row-meta">{meta}</span>}
      {(to ?? onClick) && (
        <ChevronRight
          size={15}
          className="adm-row-chevron"
          aria-hidden="true"
        />
      )}
    </>
  );
  if (to) {
    return (
      <Link to={to} className="adm-row" data-testid={testId}>
        {inner}
      </Link>
    );
  }
  if (onClick) {
    return (
      <button
        type="button"
        className="adm-row"
        onClick={onClick}
        data-testid={testId}
      >
        {inner}
      </button>
    );
  }
  return (
    <div className="adm-row" data-testid={testId}>
      {inner}
    </div>
  );
};

/** Список строк ListRow с разделителями: каждый ребёнок становится пунктом списка. */
export const SectionList = ({
  children,
  label,
  testId,
}: {
  children: ReactNode;
  label?: string | undefined;
  testId?: string | undefined;
}) => (
  <ul className="adm-list" aria-label={label} data-testid={testId}>
    {Children.toArray(children).map((child, index) => (
      <li key={isValidElement(child) && child.key != null ? child.key : index}>
        {child}
      </li>
    ))}
  </ul>
);

Section.displayName = "Section";
ListRow.displayName = "ListRow";
SettingRow.displayName = "SettingRow";
