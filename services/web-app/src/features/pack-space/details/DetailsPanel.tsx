import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { pickLocalized } from "@shared/lib/i18n/pickLocalized";
import { useSpace } from "../context/SpaceContext";
import { DetailsActions } from "./DetailsActions";
import { EditDelta, EditHistory } from "./EditFeedback";
import { ElementHeader } from "./ElementHeader";
import { EmptyDetails } from "./EmptyDetails";
import { MoreMenu } from "./MoreMenu";
import { TechnicalDetails } from "./TechnicalDetails";
import { WhatIfSection } from "./WhatIfSection";
import { WhySection } from "./WhySection";
import { EditSection } from "./edit/EditSection";
import { editTargets } from "./edit/targets";
import { useConditionEdit } from "./edit/useConditionEdit";
import { explainToSentences, whatIfRows } from "./explain";
import { useDetailsData } from "./useDetailsData";
import "./space-details.css";

/**
 * Правая панель «Результата» (pack-studio-ux.md, 5.4): всегда о выбранном. Ничего не выбрано:
 * «Что здесь можно сделать». Выбран элемент: заголовок, «Почему так», «Что изменится, если…»,
 * «Изменить условия» (или «Править копию» у выпущенной версии), «Технические подробности»,
 * «Ещё». Правка условия идёт мини-формами прямо в панели.
 */
export const DetailsPanel = ({
  initialEditing = false,
}: {
  /** Форма правки открыта сразу (галерея и тесты). */
  initialEditing?: boolean;
}) => {
  const { t, i18n } = useTranslation("packSpace");
  const { released } = useSpace();
  const data = useDetailsData();
  const edit = useConditionEdit(data.outcome, data.checks);
  const { element, explain, info, group, words } = data;
  const [editing, setEditing] = useState(initialEditing);
  const [historyOpen, setHistoryOpen] = useState(false);
  // Сколько правок было в ленте, когда форма открылась: «Отменить» откатывает до этого места.
  const [startCursor, setStartCursor] = useState(0);
  const [revertTo, setRevertTo] = useState<number | null>(null);
  const elementKey = element ? `${element.section}:${element.id}` : "";
  const [seenKey, setSeenKey] = useState(elementKey);
  // Другой элемент: форма закрывается, она принадлежала прежнему.
  if (seenKey !== elementKey) {
    setSeenKey(elementKey);
    setEditing(false);
    setRevertTo(null);
  }

  const chain = explain.data?.chain;
  const sentences = useMemo(
    () => (chain ? explainToSentences(chain, { t, words, group }) : []),
    [chain, t, words, group],
  );
  const rows = useMemo(
    () =>
      explain.data
        ? whatIfRows(explain.data, data.shown?.inputs, { t, words, group })
        : [],
    [explain.data, data.shown?.inputs, t, words, group],
  );
  const { targets, other } = useMemo(() => editTargets(chain ?? []), [chain]);
  const names = useMemo(() => {
    const out = new Map<string, string>();
    const lang = i18n.language;
    for (const form of data.shown?.forms ?? []) {
      for (const field of form.fields) {
        out.set(field.id, pickLocalized(field.label, lang, field.id));
      }
    }
    for (const rule of data.checks ?? []) {
      out.set(rule.id, pickLocalized(rule.title, lang, rule.id));
    }
    return out;
  }, [data.shown, data.checks, i18n.language]);

  // «Отменить» в форме: откат по одной правке, пока не вернёмся к месту открытия формы.
  const cursor = edit.history.cursor;
  const { notice, busy } = edit;
  const undoRef = useRef(edit.undo);
  useEffect(() => {
    undoRef.current = edit.undo;
  });
  // Откат дошёл до места открытия формы (или упёрся в отказ): форма закрывается.
  if (revertTo !== null && !busy && (notice !== null || cursor <= revertTo)) {
    setRevertTo(null);
    if (notice === null) setEditing(false);
  }
  useEffect(() => {
    if (revertTo === null || busy || notice !== null || cursor <= revertTo) {
      return;
    }
    undoRef.current();
  }, [revertTo, cursor, busy, notice]);

  const { begin } = edit;
  useEffect(() => {
    if (initialEditing) begin();
  }, [initialEditing, begin]);

  if (!element || !info) return <EmptyDetails edit={edit} />;

  const editable = explain.data ? targets.length > 0 : null;
  return (
    <div className="sp-details" data-testid="sp-details">
      <div className="sp-details-handle" aria-hidden="true" />
      <div className="sp-details-top">
        <ElementHeader
          id={element.id}
          info={info}
          group={group}
          state={data.state}
          outcome={data.shown}
        />
        <MoreMenu
          edit={edit}
          historyOpen={historyOpen}
          onHistory={() => {
            setHistoryOpen((open) => !open);
          }}
        />
      </div>
      <EditDelta edit={edit} />
      <WhySection
        query={explain}
        sentences={sentences}
        dependsOnInputs={rows.length > 0}
      />
      {explain.data && <WhatIfSection rows={rows} words={words} />}
      {editing && (
        <EditSection
          edit={edit}
          targets={targets}
          other={other}
          words={words}
          names={names}
          changed={cursor - startCursor}
          onDone={() => {
            setEditing(false);
          }}
          onCancel={() => {
            setRevertTo(startCursor);
          }}
        />
      )}
      <DetailsActions
        element={element}
        released={released || edit.blocked === "released"}
        registry={edit.blocked === "registry"}
        editable={editable}
        editing={editing}
        onEdit={() => {
          edit.begin();
          setStartCursor(cursor);
          setEditing(true);
        }}
      />
      {historyOpen && <EditHistory edit={edit} />}
      {chain && <TechnicalDetails element={element} chain={chain} />}
      <div
        className="sr-only"
        role="status"
        aria-live="polite"
        data-testid="sp-edit-live"
      >
        {edit.live}
      </div>
    </div>
  );
};

export default DetailsPanel;
