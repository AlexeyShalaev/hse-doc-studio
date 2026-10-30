import type { ReactNode } from "react";
import { clsx } from "clsx";

// Каркас страницы админки: одинаковые поля, ширина и заголовок на всех
// разделах. Ширина «wide» для таблиц и сводок, «narrow» для форм настроек.

export type PageWidth = "wide" | "narrow" | "full";

export type PageContainerProps = {
  width?: PageWidth | undefined;
  children: ReactNode;
  testId?: string | undefined;
  className?: string | undefined;
};

/** Поля и предельная ширина содержимого. Растягивается на всю высоту, чтобы StickySaveBar прилипал к низу. */
export const PageContainer = ({
  width = "wide",
  children,
  testId,
  className,
}: PageContainerProps) => (
  <div
    className={clsx("adm-page", className)}
    data-width={width}
    data-testid={testId}
  >
    {children}
  </div>
);

export type PageTab<T extends string = string> = {
  id: T;
  label: string;
  /** Число рядом с подписью: сколько записей во вкладке. */
  count?: number | undefined;
  /** Тон числа: accent, когда там ждут решения. */
  countTone?: "neutral" | "accent" | "warning" | "danger" | undefined;
  testId?: string | undefined;
};

export type PageTabsProps<T extends string> = {
  tabs: readonly PageTab<T>[];
  value: T;
  onChange: (id: T) => void;
  /** Название набора вкладок для скринридера. */
  label: string;
  /** id панели, которой управляют вкладки (aria-controls). */
  panelId?: string | undefined;
  /** Префикс id кнопок: `${idPrefix}-${tab.id}`, для aria-labelledby панели. */
  idPrefix?: string | undefined;
};

/** Вкладки раздела: ставятся сразу под заголовком через PageHeader.tabs. */
export const PageTabs = <T extends string>({
  tabs,
  value,
  onChange,
  label,
  panelId,
  idPrefix,
}: PageTabsProps<T>) => (
  <div role="tablist" aria-label={label} className="adm-tabs">
    {tabs.map((tab) => {
      const selected = tab.id === value;
      return (
        <button
          key={tab.id}
          type="button"
          role="tab"
          id={idPrefix ? `${idPrefix}-${tab.id}` : undefined}
          aria-selected={selected}
          aria-controls={panelId}
          tabIndex={selected ? 0 : -1}
          data-testid={tab.testId}
          className="adm-tab"
          onClick={() => {
            onChange(tab.id);
          }}
          onKeyDown={(event) => {
            if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") return;
            event.preventDefault();
            const index = tabs.findIndex((t) => t.id === value);
            const step = event.key === "ArrowRight" ? 1 : -1;
            const next = tabs[(index + step + tabs.length) % tabs.length];
            if (!next) return;
            onChange(next.id);
            const list = event.currentTarget.parentElement;
            const buttons =
              list?.querySelectorAll<HTMLButtonElement>("[role=tab]");
            buttons?.[tabs.indexOf(next)]?.focus();
          }}
        >
          {tab.label}
          {tab.count !== undefined && (
            <span className="adm-count" data-tone={tab.countTone ?? "neutral"}>
              {tab.count}
            </span>
          )}
        </button>
      );
    })}
  </div>
);

export type PageHeaderProps = {
  title: ReactNode;
  /** Одна строка о том, что здесь делают. */
  description?: ReactNode | undefined;
  /** Кнопки справа от заголовка. */
  actions?: ReactNode | undefined;
  /** Вкладки прямо под заголовком (PageTabs). */
  tabs?: ReactNode | undefined;
  /** Ссылка «назад» над заголовком: для вложенных страниц. */
  back?: ReactNode | undefined;
  /** Строка под описанием: метки, slug, роль. */
  meta?: ReactNode | undefined;
  testId?: string | undefined;
};

/** Заголовок страницы: h1, описание, действия справа, вкладки под ним. */
export const PageHeader = ({
  title,
  description,
  actions,
  tabs,
  back,
  meta,
  testId,
}: PageHeaderProps) => (
  <div className="adm-pagehead" data-testid={testId}>
    {back}
    <header className="adm-header">
      <div className="adm-header-text">
        <h1>{title}</h1>
        {description && <p className="adm-header-desc">{description}</p>}
        {meta && (
          <div
            className="flex items-center"
            style={{ gap: 8, flexWrap: "wrap", marginTop: 4 }}
          >
            {meta}
          </div>
        )}
      </div>
      {actions && <div className="adm-header-actions">{actions}</div>}
    </header>
    {tabs}
  </div>
);

export type AdminPageProps = Omit<PageHeaderProps, "testId"> & {
  width?: PageWidth | undefined;
  children?: ReactNode | undefined;
  /** testid всей страницы; у заголовка свой, headerTestId. */
  pageTestId?: string | undefined;
  headerTestId?: string | undefined;
};

/** Страница целиком: поля и ширина, заголовок, содержимое. */
export const AdminPage = ({
  width = "wide",
  children,
  pageTestId,
  headerTestId,
  ...header
}: AdminPageProps) => (
  <PageContainer width={width} testId={pageTestId}>
    <PageHeader {...header} testId={headerTestId} />
    {children}
  </PageContainer>
);

AdminPage.displayName = "AdminPage";
PageHeader.displayName = "PageHeader";
PageContainer.displayName = "PageContainer";
