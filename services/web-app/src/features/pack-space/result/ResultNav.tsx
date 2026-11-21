import { useMemo, type ReactNode } from "react";
import {
  CalendarDays,
  ClipboardList,
  FileText,
  Layers,
  PenLine,
  SlidersHorizontal,
  Users,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { useSpaceNav } from "../context/useSpaceNav";
import { PART_IDS, countResult, navCount, type PartId } from "./model";
import { useParts } from "./partsStore";
import { useResultData } from "./useResultData";
import "./space-result.css";

const ICONS: Record<PartId, ReactNode> = {
  documents: <FileText size="1rem" />,
  data: <ClipboardList size="1rem" />,
  people: <Users size="1rem" />,
  deadlines: <CalendarDays size="1rem" />,
  signatures: <PenLine size="1rem" />,
};

/**
 * Левая колонка «Результата»: оглавление частей с числами. Нажатие раскрывает часть и
 * прокручивает к ней, текущая часть подсвечена (её определяет прокрутка центра). Ниже две
 * ссылки в «Проверку»: редкие обзоры, которые больше не вкладки (pack-studio-ux.md, 4.1).
 */
const ResultNav = () => {
  const { t } = useTranslation("packSpace");
  const { outcome } = useResultData();
  const parts = useParts();
  const nav = useSpaceNav();
  const counts = useMemo(
    () => (outcome ? countResult(outcome) : null),
    [outcome],
  );
  return (
    <nav
      className="sp-toc"
      aria-label={t("result.navTitle")}
      data-testid="sp-toc"
    >
      <p className="sp-kicker">{t("result.navTitle")}</p>
      {PART_IDS.map((id) => (
        <button
          key={id}
          type="button"
          className="sp-toc-item"
          aria-current={parts.current === id ? "location" : undefined}
          data-testid={`sp-toc-${id}`}
          onClick={() => {
            parts.reveal(id);
          }}
        >
          <span className="sp-toc-icon" aria-hidden="true">
            {ICONS[id]}
          </span>
          <span className="sp-toc-name">{t(`result.parts.${id}`)}</span>
          {counts ? (
            <span className="sp-toc-count">{navCount(counts, id)}</span>
          ) : null}
        </button>
      ))}
      <hr className="sp-toc-rule" />
      <p className="sp-kicker">{t("result.navMore")}</p>
      <Link
        className="sp-toc-item"
        to={nav.href({ tab: "check", part: "map" })}
        data-testid="sp-toc-map"
      >
        <span className="sp-toc-icon" aria-hidden="true">
          <SlidersHorizontal size="1rem" />
        </span>
        <span className="sp-toc-name">{t("result.navMap")}</span>
      </Link>
      <Link
        className="sp-toc-item"
        to={nav.href({ tab: "check", part: "cases" })}
        data-testid="sp-toc-cases"
      >
        <span className="sp-toc-icon" aria-hidden="true">
          <Layers size="1rem" />
        </span>
        <span className="sp-toc-name">{t("result.navCases")}</span>
      </Link>
    </nav>
  );
};

export default ResultNav;
