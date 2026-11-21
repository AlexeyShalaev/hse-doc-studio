import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useSituation } from "../context/useSituation";
import type { WhatIfRow } from "./explain";
import { soft, type Words } from "./words";

/** Сколько вариантов видно сразу, остальные под «Показать ещё». */
const VISIBLE = 4;

type Applied = {
  input: string;
  value: string;
  /** Значение условия до применения (его могло не быть: тогда вернётся умолчание). */
  previous: string | undefined;
};

type WhatIfSectionProps = {
  rows: readonly WhatIfRow[];
  words: Words;
};

/**
 * «Что изменится, если…»: соседние значения условий, которые сервер уже пересчитал. Нажатие
 * ставит это условие на экран (результат пересчитается), «Вернуть» возвращает прежнее значение.
 */
export const WhatIfSection = ({ rows, words }: WhatIfSectionProps) => {
  const { t } = useTranslation("packSpace");
  const situation = useSituation();
  const [applied, setApplied] = useState<Applied | null>(null);
  const [all, setAll] = useState(false);
  const shown = all ? rows : rows.slice(0, VISIBLE);
  return (
    <section
      className="sp-details-block"
      aria-labelledby="sp-whatif-title"
      data-testid="sp-whatif"
    >
      <h4 className="sp-details-sub" id="sp-whatif-title">
        {t("details.whatIf.title")}
      </h4>
      {applied && (
        <div
          className="sp-details-applied"
          role="status"
          data-testid="sp-whatif-applied"
        >
          <span>
            {t("details.whatIf.applied", {
              condition: soft(words.subject(applied.input)),
              value: soft(words.value(applied.input, applied.value)),
            })}
          </span>
          <button
            type="button"
            className="btn sm"
            data-testid="sp-whatif-restore"
            onClick={() => {
              situation.setInput(applied.input, applied.previous ?? null);
              setApplied(null);
            }}
          >
            {t("details.whatIf.restore")}
          </button>
        </div>
      )}
      {rows.length === 0 ? (
        <p className="sp-details-muted" data-testid="sp-whatif-none">
          {t("details.whatIf.none")}
        </p>
      ) : (
        <ul className="sp-whatif">
          {shown.map((row) => (
            <li key={`${row.input}=${row.value}`}>
              <button
                type="button"
                className="sp-whatif-btn"
                data-testid="sp-whatif-row"
                onClick={() => {
                  setApplied({
                    input: row.input,
                    value: row.value,
                    previous: situation.inputs[row.input],
                  });
                  situation.setInput(row.input, row.value);
                }}
              >
                <span className="sp-whatif-cond">
                  {t("details.whatIf.if", {
                    condition: soft(row.inputLabel),
                    value: soft(row.valueLabel),
                  })}
                </span>
                <span className="sp-whatif-then">{row.text}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
      {rows.length > VISIBLE && (
        <button
          type="button"
          className="btn sm ghost"
          aria-expanded={all}
          onClick={() => {
            setAll((on) => !on);
          }}
        >
          {all
            ? t("details.whatIf.less")
            : t("details.whatIf.more", { count: rows.length - VISIBLE })}
        </button>
      )}
    </section>
  );
};
