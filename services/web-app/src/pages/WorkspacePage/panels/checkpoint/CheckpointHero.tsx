import { useState } from "react";
import { useTranslation } from "react-i18next";
import { clsx } from "clsx";
import { Check, ChevronDown } from "lucide-react";
import type { CheckpointReadiness, ReadinessTally } from "@entities/submission";
import { ReadinessRing } from "@shared/ui";
import { splitDescription } from "../../lib/splitDescription";

/** Длиннее — хвост описания сворачивается: у профиля ГИА он на 1489 знаков. */
const REST_CLAMP_MIN_CHARS = 700;

export type CheckpointHeroProps = {
  name: string;
  description: string;
  readiness: CheckpointReadiness;
  isPacked: boolean;
};

type StatProps = {
  tally: ReadinessTally;
  label: string;
};

const Stat = ({ tally, label }: StatProps) => {
  if (tally.total === 0) return null;
  const isDone = tally.done === tally.total;
  return (
    <div className="flex flex-col" style={{ gap: "0.125rem" }}>
      <span
        className="cp-stat-value"
        style={{ color: isDone ? "var(--c-ok)" : "var(--fg-0)" }}
      >
        {tally.done}
        <span style={{ color: "var(--fg-3)", fontWeight: 400 }}>
          /{tally.total}
        </span>
      </span>
      <span
        className="label-up"
        style={{
          fontSize: "0.59375rem",
          letterSpacing: "0.1em",
          color: "var(--fg-3)",
        }}
      >
        {label}
      </span>
    </div>
  );
};

/**
 * Шапка экрана контрольной точки, набранная как титул документа.
 *
 * Прежняя версия зажимала описание на 445–1489 знаков в колонку ~700px, а
 * справа держала пол-экрана пустоты с кольцом. Здесь ширина отдана тексту, а
 * вердикт («готов / не готов») стоит ВЫШЕ описания: студенту за день до
 * дедлайна не следует читать инструкцию, чтобы узнать, всё ли собрано.
 */
export const CheckpointHero = ({
  name,
  description,
  readiness,
  isPacked,
}: CheckpointHeroProps) => {
  const { t } = useTranslation("workbench");
  const [isRestOpen, setIsRestOpen] = useState(false);

  const { lead, rest } = splitDescription(description);
  const restParagraphs = rest.split(/\n+/).filter((p) => p.trim() !== "");
  const isClamped = rest.length > REST_CLAMP_MIN_CHARS && !isRestOpen;

  // Цифру показываем только когда есть что считать: «Готово 0 из 0» студент
  // прочитает как «ничего не готово», хотя состав точки просто не описан.
  const hasFigure = !readiness.isUnknown && readiness.total > 0;
  const ratio = hasFigure ? readiness.done / readiness.total : 0;
  const readinessLabel = t("checkpoint.readiness", {
    done: readiness.done,
    total: readiness.total,
  });

  return (
    <header>
      <div className="flex items-center" style={{ gap: "0.625rem" }}>
        <span
          className="label-up"
          style={{
            fontSize: "0.59375rem",
            letterSpacing: "0.14em",
            color: "var(--fg-3)",
          }}
        >
          {t("checkpoint.title")}
        </span>
        <span style={{ flex: 1, height: 1, background: "var(--border)" }} />
        {isPacked && (
          <span className="chip subtle" style={{ flexShrink: 0 }}>
            <Check size="0.6875rem" style={{ color: "var(--c-ok)" }} />
            {t("submit.packed")}
          </span>
        )}
      </div>

      <h1 className="cp-title" style={{ marginTop: "0.75rem" }}>
        {name}
      </h1>

      {lead !== "" && <p className="cp-lead">{lead}</p>}

      <div className="cp-band">
        {hasFigure ? (
          <>
            <div className="flex items-center" style={{ gap: "0.625rem" }}>
              <ReadinessRing
                done={readiness.done}
                total={readiness.total}
                size={44}
                label={readinessLabel}
              />
              <div className="flex flex-col" style={{ gap: 1 }}>
                <strong style={{ fontSize: "0.875rem" }}>
                  {readinessLabel}
                </strong>
                <span
                  className="dim"
                  style={{
                    fontSize: "0.71875rem",
                    color: readiness.isComplete ? "var(--c-ok)" : "var(--fg-2)",
                  }}
                >
                  {readiness.isComplete
                    ? t("checkpoint.allReady")
                    : t("checkpoint.remaining", { count: readiness.blockers })}
                </span>
              </div>
            </div>

            {/* Тот же счёт, разрезанный по осям: сумма сходится с кольцом по
                построению (ReadinessBreakdown), поэтому «где именно просело»
                не может разойтись с «сколько всего осталось». */}
            <div className="cp-stats">
              <Stat
                tally={readiness.breakdown.documents}
                label={t("checkpoint.sectionDocs")}
              />
              <Stat
                tally={readiness.breakdown.signatures}
                label={t("checkpoint.sectionSignatures")}
              />
              <Stat
                tally={readiness.breakdown.forms}
                label={t("checkpoint.sectionForms")}
              />
            </div>

            <div
              className="progress"
              style={{ flex: 1, minWidth: "8.75rem", marginLeft: "auto" }}
            >
              <div
                style={{
                  width: `${String(Math.round(ratio * 100))}%`,
                  background: readiness.isComplete
                    ? "var(--c-ok)"
                    : "var(--accent)",
                }}
              />
            </div>
          </>
        ) : (
          <span className="dim" style={{ fontSize: "0.78125rem" }}>
            {t("checkpoint.noItems")}
          </span>
        )}
      </div>

      {restParagraphs.length > 0 && (
        <>
          <div className={clsx("cp-rest", isClamped && "clamped")}>
            {restParagraphs.map((paragraph) => (
              <p key={paragraph.slice(0, 40)}>{paragraph}</p>
            ))}
          </div>
          {rest.length > REST_CLAMP_MIN_CHARS && (
            <button
              type="button"
              className="btn xs ghost"
              style={{ marginTop: "0.5rem" }}
              onClick={() => {
                setIsRestOpen((open) => !open);
              }}
            >
              <ChevronDown
                size="0.6875rem"
                style={{
                  transform: isRestOpen ? "rotate(180deg)" : undefined,
                  transition: "transform 0.15s var(--ease)",
                }}
              />
              {isRestOpen ? t("checkpoint.descLess") : t("checkpoint.descMore")}
            </button>
          )}
        </>
      )}
    </header>
  );
};
