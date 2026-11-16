import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { OutcomeElementRef, PackOutcome } from "@entities/pack-studio";
import { describeElement } from "../../lib/elements";
import { useOutcomeModel } from "../../model";

const SHOWN = 8;

type ReadersProps = {
  readers: readonly OutcomeElementRef[];
  outcome: PackOutcome | undefined;
};

/** Соседи по правилам: другие элементы, о которых говорят те же решения; клик выбирает элемент. */
export const Readers = ({ readers, outcome }: ReadersProps) => {
  const { t, i18n } = useTranslation("packOutcome");
  const { select } = useOutcomeModel();
  const [all, setAll] = useState(false);
  if (readers.length === 0) return null;
  const shown = all ? readers : readers.slice(0, SHOWN);
  return (
    <section
      className="po-rules-block"
      aria-labelledby="po-readers-title"
      data-testid="outcome-readers"
    >
      <h3 className="po-rules-sub" id="po-readers-title">
        {t("rules.readers.title")}
        <span className="po-group-count">{readers.length}</span>
      </h3>
      <p className="po-note">{t("rules.readers.lead")}</p>
      <ul className="po-readers">
        {shown.map((el) => {
          const info = describeElement(outcome, el, i18n.language);
          return (
            <li key={`${el.section}:${el.id}`}>
              <button
                type="button"
                className="po-reader"
                data-testid={`outcome-reader-${el.section}-${el.id}`}
                onClick={() => {
                  select(el);
                }}
              >
                <span className="po-mark">{t(`sections.${el.section}`)}</span>
                <span className="po-reader-title">
                  {info.kind === "route_step"
                    ? t("rules.stepTitle", {
                        n: info.step ?? 0,
                        point: info.point ?? "",
                      })
                    : info.title}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
      {readers.length > SHOWN && (
        <button
          type="button"
          className="po-link"
          aria-expanded={all}
          data-testid="outcome-readers-toggle"
          onClick={() => {
            setAll(!all);
          }}
        >
          {all
            ? t("rules.readers.less")
            : t("rules.readers.more", { count: readers.length - SHOWN })}
        </button>
      )}
    </section>
  );
};
