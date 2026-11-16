import { useId, type ReactNode } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  useSectionCollapse,
  type SectionCollapse,
} from "../../lib/sectionCollapse";

export type SectionId =
  | "documents"
  | "meta"
  | "participants"
  | "points"
  | "route"
  | "checks"
  | "branches";

type SectionShellProps = {
  id: SectionId;
  /** Состояние свёрнутости снаружи (раздел грузит данные только раскрытым). */
  collapse?: SectionCollapse;
  title: string;
  /** Счётчик в заголовке («14 из 18 в комплекте»); пусто, пока результата нет. */
  count: string | null;
  /** Результата ещё нет: вместо тела скелет. */
  loading: boolean;
  children: ReactNode;
};

/**
 * Сворачиваемый раздел результата: заголовок-счётчик, состояние свёрнутости запоминается.
 * Срезы F3, F4 и F5 кладут своё содержимое в `children` и не трогают оболочку.
 */
export const SectionShell = ({
  id,
  collapse,
  title,
  count,
  loading,
  children,
}: SectionShellProps) => {
  const { t } = useTranslation("packOutcome");
  const own = useSectionCollapse(id);
  const [collapsed, setCollapsed] = collapse ?? own;
  const bodyId = useId();
  const Chevron = collapsed ? ChevronRight : ChevronDown;
  return (
    <section
      className="po-section"
      aria-labelledby={`${bodyId}-h`}
      data-testid={`outcome-section-${id}`}
      data-collapsed={collapsed ? "true" : undefined}
    >
      <h3 className="po-section-head" id={`${bodyId}-h`}>
        <button
          type="button"
          className="po-section-toggle"
          aria-expanded={!collapsed}
          aria-controls={bodyId}
          title={t(collapsed ? "sections.expand" : "sections.collapse", {
            name: title,
          })}
          onClick={() => {
            setCollapsed(!collapsed);
          }}
        >
          <Chevron size="0.875rem" aria-hidden="true" />
          <span className="po-section-title">{title}</span>
          {count !== null && (
            <span
              className="po-section-count"
              data-testid={`outcome-count-${id}`}
            >
              {count}
            </span>
          )}
        </button>
      </h3>
      <div id={bodyId} className="po-section-body" hidden={collapsed}>
        {loading ? (
          <div className="po-skeleton" aria-hidden="true">
            <div className="shimmer po-skeleton-row" />
            <div className="shimmer po-skeleton-row" data-short="true" />
            <div className="shimmer po-skeleton-row" />
          </div>
        ) : (
          children
        )}
      </div>
    </section>
  );
};

/** Содержимое раздела, которого пока нет: честная заглушка, а не пустое место. */
export const SectionStub = () => {
  const { t } = useTranslation("packOutcome");
  return <p className="po-stub">{t("sections.stub")}</p>;
};
