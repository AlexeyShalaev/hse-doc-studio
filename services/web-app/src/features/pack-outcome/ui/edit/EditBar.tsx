import { Redo2, Undo2, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { tallyDelta } from "../../lib/edit/delta";
import type { RuleEdit } from "../../lib/edit/plan";
import { useOutcomeModel } from "../../model";
import { useRuleEdit } from "./context";
import { EditNoticeView } from "./RuleEditor";
import "./edit.css";

const clock = (at: number, lang: string): string =>
  new Date(at).toLocaleTimeString(lang, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });

/** Подпись записи в ленте: что за правило, где, и что с ним сделали. */
const useEditText = () => {
  const { t } = useTranslation("packOutcome");
  return (edit: RuleEdit): string => {
    const rule =
      edit.action === "delete"
        ? t(`edit.record.${edit.subject}`, { defaultValue: edit.subject })
        : t(`rules.kinds.${edit.subject}`, { defaultValue: edit.subject });
    return t(`edit.entry.${edit.action}${edit.place === "" ? "" : "At"}`, {
      rule,
      place: edit.place,
    });
  };
};

/**
 * Полоса правок над панелью «Правила и причины»: «Отменить» и «Повторить», лента правок этого
 * экрана, плашки отказов и сравнение результата до и после. Видна, когда правка началась.
 */
export const EditBar = () => {
  const { t, i18n } = useTranslation("packOutcome");
  const ui = useRuleEdit();
  const { select } = useOutcomeModel();
  const text = useEditText();
  if (!ui?.available) return null;
  const { history, delta } = ui;
  const notice = ui.notice?.source === "history" ? ui.notice : null;
  if (history.entries.length === 0 && !delta && !notice) return null;
  const top = history.cursor - 1;
  const tally = delta ? tallyDelta(delta.items) : null;
  const locked = ui.blocked !== null || ui.busy;
  return (
    <section
      className="po-edit-bar"
      aria-label={t("edit.bar.label")}
      data-testid="outcome-edit-bar"
    >
      <div
        className="po-edit-tools"
        role="toolbar"
        aria-label={t("edit.bar.label")}
      >
        <button
          type="button"
          className="btn sm"
          aria-label={t("edit.undo")}
          title={t("edit.undoHint")}
          disabled={!ui.canUndo || locked}
          data-testid="outcome-edit-undo"
          onClick={ui.undo}
        >
          <Undo2 size="0.875rem" aria-hidden="true" />
          {t("edit.undo")}
        </button>
        <button
          type="button"
          className="btn sm"
          aria-label={t("edit.redo")}
          title={t("edit.redoHint")}
          disabled={!ui.canRedo || locked}
          data-testid="outcome-edit-redo"
          onClick={ui.redo}
        >
          <Redo2 size="0.875rem" aria-hidden="true" />
          {t("edit.redo")}
        </button>
      </div>
      {notice && <EditNoticeView notice={notice} onDismiss={ui.clearNotice} />}
      {delta && tally && (
        <div className="po-edit-delta" data-testid="outcome-edit-delta">
          <div className="po-edit-delta-head">
            <p className="po-edit-delta-title">
              {delta.items.length === 0
                ? t("edit.delta.same")
                : t(`edit.delta.title.${delta.direction}`)}
            </p>
            <button
              type="button"
              className="icon-btn sm"
              aria-label={t("edit.delta.dismiss")}
              title={t("edit.delta.dismiss")}
              onClick={ui.dismissDelta}
            >
              <X size="0.875rem" aria-hidden="true" />
            </button>
          </div>
          {delta.items.length > 0 && (
            <>
              <p
                className="po-edit-delta-tally"
                data-testid="outcome-edit-delta-tally"
              >
                <span data-kind="added">{`+${String(tally.added)}`}</span>
                <span data-kind="changed">{`~${String(tally.changed)}`}</span>
                <span data-kind="removed">{`−${String(tally.removed)}`}</span>
              </p>
              <ul className="po-edit-delta-list">
                {delta.items.map((item) => (
                  <li
                    key={`${item.section}:${item.id}`}
                    data-symbol={item.symbol}
                    data-testid="outcome-edit-delta-item"
                  >
                    <span className="po-edit-sign" aria-hidden="true">
                      {item.symbol === "-" ? "−" : item.symbol}
                    </span>
                    <span className="po-edit-delta-text">
                      <span className="sr-only">
                        {t(`edit.delta.symbol.${item.symbol}`)}:{" "}
                      </span>
                      <button
                        type="button"
                        className="po-edit-link"
                        onClick={() => {
                          select({ section: item.section, id: item.id });
                        }}
                      >
                        {item.label}
                      </button>{" "}
                      <span className="po-note">
                        {t(`sections.${item.section}`)}
                        {item.symbol === "~" &&
                        item.before !== null &&
                        item.after !== null
                          ? `: ${t("edit.delta.from", { before: item.before, after: item.after })}`
                          : ""}
                      </span>
                    </span>
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}
      {history.entries.length > 0 && (
        <details className="po-edit-history" data-testid="outcome-edit-history">
          <summary>
            {t("edit.history.title", { count: history.entries.length })}
          </summary>
          <ol className="po-edit-entries" reversed>
            {[...history.entries]
              .map((edit, index) => ({ edit, index }))
              .reverse()
              .map(({ edit, index }) => {
                const applied = index < history.cursor;
                return (
                  <li
                    key={edit.id}
                    data-state={applied ? "applied" : "undone"}
                    data-testid="outcome-edit-entry"
                  >
                    <span className="po-edit-entry-text">{text(edit)}</span>
                    <span className="po-note">
                      {clock(edit.at, i18n.language)}
                      {" · "}
                      {t(
                        applied
                          ? "edit.history.applied"
                          : "edit.history.undone",
                      )}
                    </span>
                    {index === top && (
                      <button
                        type="button"
                        className="btn sm"
                        aria-label={`${t("edit.undo")}: ${text(edit)}`}
                        disabled={locked}
                        data-testid="outcome-edit-entry-undo"
                        onClick={ui.undo}
                      >
                        {t("edit.undo")}
                      </button>
                    )}
                    {index === history.cursor && (
                      <button
                        type="button"
                        className="btn sm"
                        aria-label={`${t("edit.redo")}: ${text(edit)}`}
                        disabled={locked}
                        data-testid="outcome-edit-entry-redo"
                        onClick={ui.redo}
                      >
                        {t("edit.redo")}
                      </button>
                    )}
                  </li>
                );
              })}
          </ol>
        </details>
      )}
    </section>
  );
};
