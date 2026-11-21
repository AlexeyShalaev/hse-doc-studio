import { useId, type ReactNode } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { PartId } from "./model";
import { partDomId } from "./partsStore";
import "./space-result.css";

/**
 * Часть результата: заголовок-кнопка с итогом в одну строку и тело под ним. Свёрнутая часть
 * остаётся одной строкой (число и суть видны), поэтому экран читается как оглавление, а не как
 * простыня. Идентификатор в разметке нужен оглавлению слева.
 */
export const PartShell = ({
  id,
  icon,
  title,
  summary,
  open,
  onToggle,
  children,
}: {
  id: PartId;
  icon: ReactNode;
  title: string;
  summary: string;
  open: boolean;
  onToggle: () => void;
  children: ReactNode;
}) => {
  const { t } = useTranslation("packSpace");
  const bodyId = useId();
  const Chevron = open ? ChevronDown : ChevronRight;
  return (
    <section
      id={partDomId(id)}
      className="sp-part"
      data-open={open ? "true" : undefined}
      data-testid={`sp-part-${id}`}
    >
      <h2 className="sp-part-head">
        <button
          type="button"
          className="sp-part-toggle"
          aria-expanded={open}
          aria-controls={bodyId}
          title={t(open ? "result.collapse" : "result.expand", { name: title })}
          data-testid={`sp-part-${id}-toggle`}
          onClick={onToggle}
        >
          <Chevron size="0.9375rem" aria-hidden="true" />
          <span className="sp-part-icon" aria-hidden="true">
            {icon}
          </span>
          <span className="sp-part-title">{title}</span>
          <span className="sp-part-summary">{summary}</span>
        </button>
      </h2>
      <div id={bodyId} className="sp-part-body" hidden={!open}>
        {open ? children : null}
      </div>
    </section>
  );
};
